"""Announce published releases and verify the destination and saved Discord message."""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

def request_json(url, label, headers=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{label}: HTTP{error.code} {error.reason}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        reason = str(getattr(error, "reason", error))
        reason = re.sub(r"https://[^\s'\"]+", "[URL redacted]", reason)
        raise RuntimeError(f"{label}: {reason}; delivery is unconfirmed") from error

def build_payload(release, name, description, support):
    if release["draft"] or not release.get("published_at"):
        raise ValueError("release is not published")
    title = name + " " + release["tag_name"].removeprefix("v")
    if release["prerelease"]:
        title += " (pre-release)"
    description += f"\n\n[Download]({release['html_url']}) · [Support]({support})"
    return {"allowed_mentions": {"parse": []}, "embeds": [{"title": title, "url": release["html_url"], "description": description, "color": 0x7DFAAB}]}

def announce(webhook, expected_channel, payload, send, record):
    parsed = urllib.parse.urlparse(webhook)
    if parsed.scheme != "https" or parsed.hostname not in {"discord.com", "discordapp.com"} or not re.fullmatch(r"/api(?:/v[0-9]+)?/webhooks/[0-9]+/[A-Za-z0-9._-]+(?:/github)?", parsed.path):
        raise ValueError("invalid Discord webhook address")
    webhook = urllib.parse.urlunparse(parsed._replace(path=parsed.path.removesuffix("/github"), query="", fragment=""))
    headers = {"User-Agent": "DooDesch-Release-Announcement", "Content-Type": "application/json"}
    target = request_json(webhook, "read Discord destination", headers)
    if target.get("channel_id") != expected_channel:
        raise ValueError(f"Discord destination mismatch: measured {target.get('channel_id')}, required {expected_channel}")
    record.update(channel_id=expected_channel, status="checked", payload=payload)
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if not send:
        print(f"info: Discord channel {expected_channel} confirmed; announcement deliberately not sent")
        return record
    record["status"] = "attempted"
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"info: sending release announcement to Discord channel {expected_channel}")
    message = request_json(webhook + "?wait=true", "send Discord announcement", headers, payload)
    message_id = message.get("id", "")
    if not message_id or message.get("channel_id") != expected_channel:
        raise ValueError("Discord returned no matching message acknowledgement; inspect the channel before retry")
    record.update(status="acknowledged", message_id=message_id)
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"info: Discord acknowledged message {message_id}")
    saved = request_json(webhook + "/messages/" + message_id, "read saved Discord announcement", headers)
    if saved.get("id") != message_id or saved.get("channel_id") != expected_channel:
        raise ValueError("saved Discord message does not match its acknowledgement")
    record.update(status="confirmed", message_url=f"https://discord.com/channels/{target['guild_id']}/{expected_channel}/{message_id}")
    Path("discord-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"confirmed: Discord message {message_id} is saved in channel {expected_channel}")
    return record

def run():
    tag = os.environ["RELEASE_TAG"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", tag):
        raise ValueError(f"invalid release tag: {tag!r}")
    repo = os.environ["GITHUB_REPOSITORY"]
    release = request_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", "read published GitHub release", {"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"})
    if release["tag_name"] != tag:
        raise ValueError("GitHub release tag differs from requested tag")
    payload = build_payload(release, os.environ["PRODUCT_NAME"], os.environ["PRODUCT_SUMMARY"], os.environ["PRODUCT_SUPPORT"])
    webhook = os.environ.get("DISCORD_RELEASE_WEBHOOK", "")
    if not webhook:
        raise ValueError("DISCORD_RELEASE_WEBHOOK is missing; release announcement cannot run")
    result = announce(webhook, os.environ["DISCORD_CHANNEL_ID"], payload, os.environ.get("SEND_ANNOUNCEMENT") == "true", {"release_id": release["id"], "release_tag": tag, "repository": repo})
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"Discord: {result['status']}. Channel: {result['channel_id']}.\n\n" + result.get("message_url", "No message sent.") + "\n")

if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        raise SystemExit(f"error: release announcement failed: {error}") from None
