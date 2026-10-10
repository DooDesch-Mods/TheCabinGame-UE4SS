import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('distribution', ROOT / 'tools/distribution.py')
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)
LICENSE = (ROOT / 'licenses/UE4SS-MIT.txt').read_bytes().replace(b'\r\n', b'\n')

def archive(entries=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as zipped:
        for name, data in (entries or {'dwmapi.dll': b'proxy', 'ue4ss/UE4SS.dll': b'loader', 'ue4ss/LICENSE': LICENSE}).items():
            entry = zipfile.ZipInfo()
            entry.filename = name
            zipped.writestr(entry, data)
    return stream.getvalue()

def selection(data):
    return {'asset': 'UE4SS_v3.0.1-1164-g5e627997.zip', 'version': 'v3.0.1-1164-g5e627997',
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'url': 'https://example.invalid/asset.zip', 'sourceCommit': '5e627997' + '0' * 32,
            'licenseSha256': hashlib.sha256(LICENSE).hexdigest(), 'releaseNotes': 'Unchanged upstream package.'}

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.data = archive()
        self.manifest = selection(self.data)

    def test_original_archive_and_license(self):
        self.assertEqual(d.validate(self.data, self.manifest, self.manifest['licenseSha256']), self.manifest['sha256'])

    def test_reject_modified_bytes(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            d.validate(self.data + b'x', self.manifest)

    def test_reject_wrong_size(self):
        self.manifest['bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            d.validate(self.data, self.manifest)

    def test_reject_missing_loader(self):
        data = archive({'dwmapi.dll': b'proxy', 'ue4ss/LICENSE': LICENSE})
        with self.assertRaisesRegex(ValueError, 'missing original loader files'):
            d.validate(data, selection(data))

    def test_reject_unsafe_paths(self):
        for path in ('../outside.dll', '/absolute.dll', 'C:/outside.dll', 'ue4ss\\outside.dll'):
            with self.subTest(path=path):
                data = archive({'dwmapi.dll': b'proxy', 'ue4ss/UE4SS.dll': b'loader', 'ue4ss/LICENSE': LICENSE, path: b'x'})
                with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
                    d.validate(data, selection(data))

    def test_reject_case_collision(self):
        data = archive({'dwmapi.dll': b'one', 'DWMAPI.dll': b'two', 'ue4ss/UE4SS.dll': b'loader', 'ue4ss/LICENSE': LICENSE})
        with self.assertRaisesRegex(ValueError, 'duplicate archive paths'):
            d.validate(data, selection(data))

    def test_reject_symlinks(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as zipped:
            entry = zipfile.ZipInfo('dwmapi.dll')
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            zipped.writestr(entry, 'elsewhere.dll')
        data = stream.getvalue()
        with self.assertRaisesRegex(ValueError, 'symlink archive entry'):
            d.validate(data, selection(data))

    def test_reject_changed_license(self):
        data = archive({'dwmapi.dll': b'proxy', 'ue4ss/UE4SS.dll': b'loader', 'ue4ss/LICENSE': b'different'})
        with self.assertRaisesRegex(ValueError, 'license differs'):
            d.validate(data, selection(data), self.manifest['licenseSha256'])

    def test_preserve_bytes_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            source = Path(folder) / 'original.zip'
            source.write_bytes(self.data)
            target = Path(folder) / 'dist'
            result = d.prepare(self.manifest, source, target)
            self.assertEqual((target / self.manifest['asset']).read_bytes(), self.data)
            self.assertEqual(json.loads((target / self.manifest['asset']).with_suffix('.json').read_text()), result)
            self.assertTrue(result['unmodifiedUpstreamArchive'])

    def test_reject_asset_version_mismatch(self):
        self.manifest['version'] = 'v3.0.1-1165-g12345678'
        with self.assertRaisesRegex(ValueError, 'name/version mismatch'):
            d.prepare(self.manifest)

    def test_reject_short_source_commit(self):
        self.manifest['sourceCommit'] = '5e627997'
        with self.assertRaisesRegex(ValueError, 'full upstream commit'):
            d.prepare(self.manifest)

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = selection(archive())
        self.env = {'RELEASE_TAG': self.manifest['version'], 'NEXUS_APPROVED_SHA256': self.manifest['sha256']}

    def test_reject_wrong_tag(self):
        self.env['RELEASE_TAG'] = 'v3.0.1'
        with self.assertRaisesRegex(ValueError, 'release tag'):
            d.release_gate(self.manifest, self.env)

    def test_reject_absent_or_wrong_approval(self):
        for approved in ('', '0' * 64):
            with self.subTest(approved=approved):
                self.env['NEXUS_APPROVED_SHA256'] = approved
                with self.assertRaisesRegex(ValueError, 'not approved'):
                    d.release_gate(self.manifest, self.env)

    def test_changed_package_cannot_reuse_approval(self):
        self.manifest['sha256'] = '1' * 64
        with self.assertRaisesRegex(ValueError, 'not approved'):
            d.release_gate(self.manifest, self.env)

    def test_manual_default_skips_without_secret(self):
        self.env['NEXUS_FILE_GROUP_ID'] = '123'
        report = d.release_gate(self.manifest, self.env)
        self.assertFalse(report['nexus_ready'])
        self.assertIn('not requested', report['nexus_status'])

    def test_missing_first_upload_is_explicit_skip(self):
        self.env['PUBLISH_NEXUS'] = 'true'
        report = d.release_gate(self.manifest, self.env)
        self.assertFalse(report['nexus_ready'])
        self.assertIn('first loader upload', report['nexus_status'])

    def test_configured_target_requires_authentication(self):
        self.env.update(PUBLISH_NEXUS='true', NEXUS_FILE_GROUP_ID='123')
        with self.assertRaisesRegex(ValueError, 'NEXUSMODS_API_KEY is unavailable'):
            d.release_gate(self.manifest, self.env)

    def test_valid_target_can_upload(self):
        self.env.update(PUBLISH_NEXUS='true', NEXUS_FILE_GROUP_ID='123', NEXUS_MOD_ID='456', NEXUS_API_KEY='test-placeholder')
        report = d.release_gate(self.manifest, self.env)
        self.assertTrue(report['nexus_ready'])
        self.assertEqual(report['mod_id'], '456')

    def test_reject_invalid_flags_and_ids(self):
        for key, value in (('PUBLISH_NEXUS', 'yes'), ('NEXUS_FILE_GROUP_ID', 'shortUID'), ('NEXUS_MOD_ID', '0')):
            with self.subTest(key=key):
                env = {**self.env, key: value}
                with self.assertRaises(ValueError):
                    d.release_gate(self.manifest, env)

class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.data = archive()
        self.manifest = selection(self.data)
        self.asset = {'name': self.manifest['asset'], 'id': 1, 'created_at': '2026-10-09T08:29:48Z',
                      'digest': 'sha256:' + self.manifest['sha256'], 'size': len(self.data),
                      'browser_download_url': self.manifest['url']}

    def test_newest_basic_excludes_dev_and_other_files(self):
        newer = {**self.asset, 'id': 2, 'created_at': '2026-10-10T00:00:00Z', 'name': 'UE4SS_v3.0.1-1165-g12345678.zip'}
        dev = {**newer, 'id': 3, 'name': 'UE4SS_Dev_v3.0.1-1165-g12345678.zip'}
        self.assertEqual(d.latest_basic([self.asset, dev, newer]), newer)

    def test_missing_basic_asset_fails(self):
        with self.assertRaisesRegex(ValueError, 'no recognizable basic asset'):
            d.latest_basic([])

    def test_same_package_does_not_download_or_write(self):
        with patch.object(d, 'get', return_value=json.dumps({'assets': [self.asset]}).encode()) as get, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(d.candidate(self.manifest)['status'], 'unchanged')
            self.assertEqual(get.call_count, 1)

    def test_missing_digest_fails(self):
        self.asset['digest'] = None
        with patch.object(d, 'get', return_value=json.dumps({'assets': [self.asset]}).encode()):
            with self.assertRaisesRegex(ValueError, 'no usable SHA-256'):
                d.candidate(self.manifest)

    def test_new_candidate_keeps_selection_and_remains_unapproved(self):
        selected = copy.deepcopy(self.manifest)
        self.manifest['sha256'] = '0' * 64
        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'ROOT', Path(folder)), patch.dict(os.environ, {}, clear=True), patch.object(d, 'get', side_effect=[json.dumps({'assets': [self.asset]}).encode(), self.data]):
            report = d.candidate(self.manifest)
            self.assertFalse(report['approvedForNexus'])
            self.assertEqual((Path(folder) / 'dist/candidate' / selected['asset']).read_bytes(), self.data)
            self.assertEqual(self.manifest['sha256'], '0' * 64)
            self.assertFalse((Path(folder) / 'distribution.json').exists())

    def test_modified_candidate_fails_before_artifact(self):
        self.manifest['sha256'] = '0' * 64
        with tempfile.TemporaryDirectory() as folder, patch.object(d, 'ROOT', Path(folder)), patch.object(d, 'get', side_effect=[json.dumps({'assets': [self.asset]}).encode(), self.data + b'x']):
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                d.candidate(self.manifest)
            self.assertFalse((Path(folder) / 'dist').exists())

class NoticeTests(unittest.TestCase):
    def test_selected_license_hash_and_source(self):
        manifest = json.loads((ROOT / 'distribution.json').read_text())
        self.assertEqual(hashlib.sha256(LICENSE).hexdigest(), manifest['licenseSha256'])
        self.assertTrue(manifest['sourceCommit'].startswith(manifest['version'].split('-g')[-1]))

    def test_public_readme_support_and_local_links(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        required = '> 🛟 **Need help or found a bug?** Get support at [support.doodesch.de/ue4ss](https://support.doodesch.de/ue4ss).'
        self.assertIn(required, text.split('## Download')[0])
        for file in ('distribution.json', 'docs/publishing.md', 'LICENSE.md', 'CREDITS.md', 'licenses/UE4SS-MIT.txt'):
            self.assertTrue((ROOT / file).is_file(), file)
        for file in ROOT.rglob('*'):
            if file.is_file() and '.git' not in file.parts and 'dist' not in file.parts and file.suffix in {'.md', '.py', '.yml', '.json', '.txt'}:
                content = file.read_text(encoding='utf-8')
                self.assertNotIn(chr(0x2014), content, str(file))
                self.assertNotIn(chr(0x2013), content, str(file))

if __name__ == '__main__':
    unittest.main()
