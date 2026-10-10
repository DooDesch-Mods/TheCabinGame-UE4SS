"""Check original UE4SS assets and prepare version-pinned distribution packages."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://api.github.com/repos/UE4SS-RE/RE-UE4SS'
ASSET_PATTERN = re.compile(r'^UE4SS_(v\d+\.\d+\.\d+-\d+-g[0-9a-f]+)\.zip$')
REQUIRED = {'dwmapi.dll', 'ue4ss/UE4SS.dll', 'ue4ss/LICENSE'}

def get(url, api=False):
    headers = {'User-Agent': 'DooDesch-UE4SS-Distribution', 'Accept': 'application/vnd.github+json' if api else '*/*'}
    if api and (token := os.environ.get('GH_TOKEN')):
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        if response.status != 200:
            raise ValueError(f'download {url}: HTTP {response.status}')
        return response.read()

def validate(data, manifest, license_hash=None):
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest['sha256']:
        raise ValueError(f'asset SHA-256 mismatch: expected={manifest["sha256"]}, actual={digest}')
    if len(data) != manifest['bytes']:
        raise ValueError(f'asset size mismatch: expected={manifest["bytes"]}, actual={len(data)}')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError('duplicate archive paths')
        for entry in archive.infolist():
            name = entry.orig_filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or '\x00' in name:
                raise ValueError(f'unsafe archive path: {name}')
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f'symlink archive entry: {name}')
        if not REQUIRED.issubset(names):
            raise ValueError(f'missing original loader files: {sorted(REQUIRED - set(names))}')
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f'corrupt archive member: {corrupt}')
        license_data = archive.read('ue4ss/LICENSE').replace(b'\r\n', b'\n')
        if license_hash and hashlib.sha256(license_data).hexdigest() != license_hash:
            raise ValueError('archive license differs from the pinned upstream MIT license')
    return digest

def output(values):
    if path := os.environ.get('GITHUB_OUTPUT'):
        with Path(path).open('a', encoding='utf-8') as stream:
            for name, value in values.items():
                text = str(value).lower() if isinstance(value, bool) else str(value)
                if '\n' in text or '\r' in text:
                    raise ValueError(f'multiline value is not supported for output {name}')
                stream.write(f'{name}={text}\n')

def prepare(manifest, source=None, target=None):
    if manifest['asset'] != f'UE4SS_{manifest["version"]}.zip' or not ASSET_PATTERN.fullmatch(manifest['asset']):
        raise ValueError('manifest asset name/version mismatch')
    if not re.fullmatch(r'[0-9a-f]{40}', manifest['sourceCommit']):
        raise ValueError('sourceCommit must be a full upstream commit')
    data = source.read_bytes() if source else get(manifest['url'])
    digest = validate(data, manifest, manifest['licenseSha256'])
    target = target or ROOT / 'dist'
    target.mkdir(parents=True, exist_ok=True)
    archive = target / manifest['asset']
    archive.write_bytes(data)
    receipt = {**manifest, 'status': 'confirmed', 'unmodifiedUpstreamArchive': True}
    archive.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    output({'asset': archive.as_posix(), 'receipt': archive.with_suffix('.json').as_posix(), 'version': manifest['version'].removeprefix('v'), 'notes': manifest['releaseNotes']})
    return receipt

def release_gate(manifest, environment):
    if environment.get('RELEASE_TAG') != manifest['version']:
        raise ValueError('release tag does not match the selected upstream version')
    approved = environment.get('NEXUS_APPROVED_SHA256', '')
    if approved != manifest['sha256']:
        raise ValueError(f'package is not approved for publication: required SHA-256={manifest["sha256"]}, configured={approved or "absent"}')
    publish = environment.get('PUBLISH_NEXUS', 'false')
    if publish not in {'true', 'false'}:
        raise ValueError('PUBLISH_NEXUS must be true or false')
    group, mod_id = environment.get('NEXUS_FILE_GROUP_ID', ''), environment.get('NEXUS_MOD_ID', '')
    if group and not re.fullmatch(r'[1-9][0-9]*', group):
        raise ValueError('NEXUS_FILE_GROUP_ID must be the numeric API File ID')
    if mod_id and not re.fullmatch(r'[1-9][0-9]*', mod_id):
        raise ValueError('NEXUS_MOD_ID must be the numeric API Unique Mod ID')
    ready = publish == 'true' and bool(group)
    if ready and not environment.get('NEXUS_API_KEY'):
        raise ValueError('Nexus target configured but NEXUSMODS_API_KEY is unavailable')
    status = 'configured' if ready else 'deliberate skip: Nexus upload not requested' if publish == 'false' else 'deliberate skip: first loader upload/file-group ID pending'
    if ready and not mod_id:
        print('warn: Nexus changelog tab skipped because NEXUS_MOD_ID is absent', file=sys.stderr)
    return {'nexus_ready': ready, 'nexus_status': status, 'mod_id': mod_id}

def latest_basic(assets):
    candidates = [asset for asset in assets if ASSET_PATTERN.fullmatch(asset['name'])]
    if not candidates:
        raise ValueError('upstream experimental release has no recognizable basic asset')
    return max(candidates, key=lambda asset: (asset['created_at'], asset['id']))

def candidate(manifest):
    release = json.loads(get(UPSTREAM + '/releases/tags/experimental-latest', api=True))
    asset = latest_basic(release['assets'])
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest or ''):
        raise ValueError(f'upstream basic asset {asset["name"]} has no usable SHA-256 digest')
    if digest.removeprefix('sha256:') == manifest['sha256']:
        print('info: newest upstream basic package equals the selected version')
        output({'changed': False})
        return {'status': 'unchanged', 'asset': asset['name']}
    proposal = {'asset': asset['name'], 'assetId': asset['id'], 'version': ASSET_PATTERN.fullmatch(asset['name'])[1],
                'sha256': digest.removeprefix('sha256:'), 'bytes': asset['size'], 'url': asset['browser_download_url'],
                'approvedForNexus': False, 'status': 'unapproved upstream candidate'}
    data = get(proposal['url'])
    validate(data, proposal)
    directory = ROOT / 'dist/candidate'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / proposal['asset']).write_bytes(data)
    (directory / 'candidate.json').write_text(json.dumps(proposal, indent=2) + '\n', encoding='utf-8')
    output({'changed': True})
    return proposal

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['prepare', 'preflight', 'candidate'])
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'distribution.json').read_text(encoding='utf-8'))
    if args.operation == 'candidate':
        report = candidate(manifest)
    elif args.operation == 'preflight':
        report = release_gate(manifest, os.environ)
        output(report)
    else:
        report = prepare(manifest, args.source)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'error: UE4SS distribution {sys.argv[1:2]}: {error}') from error
