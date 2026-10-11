# Distribution publishing

## Selected package

`distribution.json` records the exact upstream basic asset, full source commit,
SHA-256, size and license hash. The builder downloads that asset and checks its
bytes, archive paths, required loader files and preserved upstream license.
The output ZIP is the original asset, not a repackaged loader.

Use Python 3.13. `python tools/distribution.py prepare` creates the package and
receipt under `dist`. Use `--source <original.zip>` to check a local copy.
`python -m unittest discover -s tests` runs the offline guards.

## Upstream candidates

The daily **Check upstream** workflow uses read-only permissions and also supports
manual dispatch. It selects the newest basic ZIP from `experimental-latest`,
checks the asset's reported SHA-256 and required archive files, and retains it as
an unapproved workflow artifact. No candidate changes the tracked selection,
creates a release or uploads to Nexus. If upstream omits a digest, the job fails
instead of treating the asset as verified.

Before selecting a new candidate, test game startup, the required gameplay mods,
loader logs and the affected installation/removal paths. Check its source/license
and update all manifest fields together. Record the actual game/mod versions and
validation limits in the release notes. CI checks do not replace game tests.

## Release and Nexus updates

Publish a stable GitHub release whose tag equals `distribution.json`'s version.
The workflow verifies the tagged manifest, builds the exact package and attaches
it with its receipt. `NEXUS_APPROVED_SHA256` must equal that package's SHA-256;
set it only after the relevant game/mod checks. A changed package needs a new
approval checksum. Prereleases do not start Nexus publication.

Manual dispatch takes an existing release tag. **publish_nexus** defaults to
false. An unchecked run only prepares the checked GitHub assets. The first Nexus
upload stays manual; if no file-group ID exists, a stable release records an
explicit Nexus skip. Once a target is configured, missing authentication fails
before any upload. The public repo uses the existing organization secret.

| Setting | Purpose |
|---|---|
| Variable `NEXUS_APPROVED_SHA256` | Exact package approved by the game/mod checks |
| Variable `NEXUS_FILE_GROUP_ID` | API File ID of this loader page's Main File |
| Variable `NEXUS_MOD_ID` | API Unique Mod ID for this loader page's Changelogs tab |
| Secret `NEXUSMODS_API_KEY` | Existing organizational Nexus key |

The loader has its own page and IDs. Do not reuse the Vortex extension or
ChairMarker file-group ID. Manual import of the original basic ZIP passed in
Vortex 2.8.0 with extension 0.1.1, including gameplay and purge. Mod Manager
Download stays off until the approved game mapping and download routing are checked.

The official Nexus action is pinned to
`c96019556046053aa26044b44396cd38929daf23`. Successful uploads must return a version
ID. Inspect the actual Nexus file versions before retrying a failed/timed-out
upload; it may already have created a version before a later operation failed.
