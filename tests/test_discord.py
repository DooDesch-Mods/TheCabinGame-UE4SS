"""Check announcement boundaries without Discord credentials or publication."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("discord_release", Path(__file__).resolve().parents[1] / "tools/announce-release.py")
discord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discord)

class Announcement(unittest.TestCase):
    def test_send_without_release_tag_stops_before_network(self):
        with patch.dict(os.environ, {"RELEASE_TAG": "", "SEND_ANNOUNCEMENT": "true"}), patch.object(discord, "request_json") as request:
            with self.assertRaisesRegex(ValueError, "published release tag"):
                discord.run()
            request.assert_not_called()

    def test_draft_cannot_be_announced(self):
        with self.assertRaisesRegex(ValueError, "not published"):
            discord.build_payload({"draft": True}, "Test", "Summary", "https://example.test", "https://example.test/icon.png")

    def test_pre_release_and_mentions(self):
        payload = discord.build_payload({"draft": False, "published_at": "2026-10-11", "prerelease": True, "tag_name": "v0.1.2", "html_url": "https://example.test/release"}, "Test", "Summary", "https://example.test/support", "https://example.test/icon.png")
        self.assertIn("pre-release", payload["embeds"][0]["title"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertEqual(payload["embeds"][0]["thumbnail"]["url"], "https://example.test/icon.png")

    def test_missing_thumbnail_stops_before_send(self):
        release = {"draft": False, "published_at": "2026-10-11"}
        with self.assertRaisesRegex(ValueError, "thumbnail requires"):
            discord.build_payload(release, "Test", "Summary", "https://example.test/support", "")

    def test_wrong_channel_stops_before_send(self):
        with patch.object(discord, "request_json", return_value={"channel_id": "wrong"}) as request:
            with self.assertRaisesRegex(ValueError, "destination mismatch"):
                discord.announce("https://discord.com/api/webhooks/123/test", "456", {}, True, {})
            self.assertEqual(request.call_count, 1)

    def test_manual_check_never_posts(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                with patch.object(discord, "request_json", return_value={"channel_id": "456"}) as request:
                    result = discord.announce("https://discord.com/api/webhooks/123/test/github", "456", {}, False, {})
                    self.assertEqual(result["status"], "checked")
                    self.assertEqual(request.call_count, 1)
            finally:
                os.chdir(previous)

    def test_sent_message_is_read_back(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            previous = os.getcwd()
            try:
                os.chdir(temporary)
                responses = [{"channel_id": "456", "guild_id": "789"}, {"channel_id": "456", "id": "1000"}, {"channel_id": "456", "id": "1000"}]
                with patch.object(discord, "request_json", side_effect=responses) as request:
                    result = discord.announce("https://discord.com/api/webhooks/123/test", "456", {}, True, {})
                    self.assertEqual(result["status"], "confirmed")
                    self.assertEqual(request.call_args.args[0], "https://discord.com/api/webhooks/123/test/messages/1000")
            finally:
                os.chdir(previous)

if __name__ == "__main__":
    unittest.main()
