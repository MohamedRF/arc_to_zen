<p align="center">
  <img src="assets/icon.svg" width="88" alt="arc_to_zen application icon">
</p>

<h1 align="center">arc_to_zen</h1>
<p align="center">A local-first migration tool for moving from Arc to Zen on macOS.</p>
<p align="center">
  <a href="https://github.com/MohamedRF/arc_to_zen/actions/workflows/ci.yml"><img src="https://github.com/MohamedRF/arc_to_zen/actions/workflows/ci.yml/badge.svg" alt="Tests and privacy checks"></a>
  <img src="https://img.shields.io/badge/platform-macOS%2014%2B-365fd4" alt="macOS 14 or later">
  <img src="https://img.shields.io/badge/python-3.11%2B-365fd4" alt="Python 3.11 or later">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-246953" alt="MIT license"></a>
</p>
<p align="center">
  <a href="https://github.com/MohamedRF/arc_to_zen/releases">Releases</a> ·
  <a href="docs/compatibility.md">Compatibility</a> ·
  <a href="docs/privacy.md">Privacy</a> ·
  <a href="docs/recovery.md">Recovery</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

Move Arc spaces, tabs, Essentials, and folders into Zen through a guided desktop
app or a scriptable CLI. Every migration creates full local backups, stages its
changes, and verifies the result before committing the destination profile.
Arc data is always read-only, and a separate Zen profile is the default.

**Current release: v0.2.0.** Browser formats can change. Review the
[compatibility guide](docs/compatibility.md) before migrating important data.
This is an independent project, unaffiliated with Arc or Zen.

![Desktop migration preview using fictional browser data](docs/preview.png)

## Features

| Area | Supported behavior |
| :--- | :--- |
| Workspaces | Space order, names, emoji, empty spaces, and Essentials-only spaces |
| Tabs and Essentials | Pinned and open tabs in both Zen session stores; shared Essentials scoped to their source profile |
| Folders | Nested hierarchy, sibling order, and anchors for empty folders |
| Profile separation | Arc profiles mapped to separate Zen containers |
| Appearance | Approximate workspace colours, cached favicons, and a single-toolbar layout |
| Bookmarks and history | Labelled bookmark imports that retain existing entries; supported visits deduplicated by URL, date, and type |
| Form history | Saved text-field entries when the target database schema is supported |
| Cookies | Optional Keychain access; compatible expiry and profile context retained; partitioned cookies skipped |
| Passwords | Explicit preparation of a private temporary CSV for Zen’s native importer |
| Recovery | Full backups with SHA-256 manifests and verified restoration for profile updates |

## Getting started

### Install the desktop app

Download a ZIP or DMG from [Releases](https://github.com/MohamedRF/arc_to_zen/releases)
and move **arc_to_zen.app** into Applications. Choose `arm64` for Apple Silicon or
`x64` for Intel. The packaged app requires **macOS 14 or later** and includes its
own Python runtime.

| Mac | ZIP | DMG |
| :--- | :--- | :--- |
| Apple Silicon (M1 and later) | [Download ZIP](https://github.com/MohamedRF/arc_to_zen/releases/latest/download/arc_to_zen-0.2.0-macos-arm64.zip) | [Download DMG](https://github.com/MohamedRF/arc_to_zen/releases/latest/download/arc_to_zen-0.2.0-macos-arm64.dmg) |
| Intel | [Download ZIP](https://github.com/MohamedRF/arc_to_zen/releases/latest/download/arc_to_zen-0.2.0-macos-x64.zip) | [Download DMG](https://github.com/MohamedRF/arc_to_zen/releases/latest/download/arc_to_zen-0.2.0-macos-x64.dmg) |

SHA-256 checksum files accompany each architecture on the release page.

Release builds are ad-hoc signed and are **not Apple-notarized**. Use macOS’s normal
approval flow for software you trust, or build from source. Do not disable
Gatekeeper or browser security settings.

### Migrate your data

1. **Initialize Zen.** Open a normal Zen window, then quit Zen normally to save its profile.
2. **Connect your browsers.** Select the Arc data folder and initialized Zen template profile. Keep “Create a separate Zen profile” selected for an isolated destination.
3. **Review the preview.** Click **Scan Arc**, inspect the workspace and tab counts, and choose optional imports. Scanning does not access Keychain.
4. **Quit Arc and Zen.** Click **Back up and migrate**, then review the confirmation. The app backs up both inputs, stages changes, verifies them, and commits the result.
5. **Launch the destination.** Click **Open migrated Zen**. A separate profile is not registered as Zen’s default; retain its reported path for future launches or configure it through Zen’s profile manager.

Updating the selected profile is an explicit alternative. Existing Zen data is
retained, and workspace refreshes are limited to state owned by earlier migrations.
See [Recovery](docs/recovery.md) for backup contents and restoration instructions.

### Transfer passwords

After a successful migration, select **Prepare passwords…** and approve Keychain
access in the macOS prompt. The app creates a plaintext CSV in an owner-only
folder; it does not write directly to Zen’s password store.

Use **Zen → Settings → Import Data → Passwords from CSV**, verify the import, then
select **Delete password CSV**. Conflicting passwords for the same site and
username stop preparation instead of silently choosing a value. Passkeys and
extension password vaults require their own supported transfer workflows.

## Run from source

Use **Python 3.11 or later**. Migration and Keychain access are designed for macOS;
core tests also run on Linux.

```sh
git clone https://github.com/MohamedRF/arc_to_zen.git
cd arc_to_zen
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
arc_to_zen-app
```

To explore the interface without accessing real browser data:

```sh
arc_to_zen-app --demo
```

Demo mode generates fictional fixtures and disables migration, recovery, and
password actions.

## Command-line usage

Read a count-only preview, then migrate into a separate profile:

```sh
arc_to_zen scan --arc "$HOME/Library/Application Support/Arc"

arc_to_zen migrate \
  --arc "$HOME/Library/Application Support/Arc" \
  --zen "$HOME/Library/Application Support/zen/Profiles/EXAMPLE.default" \
  --yes
```

| Option | Purpose |
| :--- | :--- |
| `--replace` | Update the selected Zen profile after a full backup |
| `--cookies` | Request Keychain access to import compatible cookies |
| `--no-history` / `--no-bookmarks` | Disable the corresponding import |
| `--no-forms` / `--no-favicons` | Disable the corresponding import |
| `--output PATH` | Choose a private runtime location outside Git and browser folders |

Manage a completed run:

```sh
arc_to_zen prepare-passwords /path/to/completed-run --yes
arc_to_zen delete-password-csv /path/to/completed-run
arc_to_zen restore /path/to/completed-replacement-run --yes
```

Run `arc_to_zen --help` or `arc_to_zen migrate --help` for all options. The previous
`arc2zen-bridge` and `arc2zen-bridge-app` commands remain available as compatibility
aliases.

## Privacy and local storage

There are no uploads, accounts, analytics, telemetry, or background update checks.
Progress logs and reports contain counts rather than browser content; recovery
metadata contains local paths needed to restore a profile. Full backups contain
private browser data and should be protected accordingly.

New installations store runs under
`~/Library/Application Support/arc_to_zen/runs`. If the legacy
`~/Library/Application Support/Arc2Zen Bridge` folder exists, the app continues
using it so previous runs remain discoverable. Existing profile ownership records
and stable migration identifiers remain compatible across the rename.

Browser output is refused inside Git repositories or either input browser folder.
The project uses generated fixtures for tests and screenshots. Never attach a
real profile, report folder, password CSV, or browser database to an issue.
Read the [privacy policy](docs/privacy.md) and [security guidance](SECURITY.md).

## Development and packaging

```sh
pytest -q
ruff check .
ruff format --check .
python scripts/check_public_tree.py
python scripts/build_macos.py
```

The macOS build generates `arc_to_zen.app`, a ZIP, a DMG, and SHA-256 checksums in
`dist/`. Builds target the host architecture. The release workflow builds Apple
Silicon and Intel artifacts for version tags matching `v*`.

The source is organized under `src/arc_to_zen/`: `gui.py` and `cli.py` provide the
interfaces, `engine.py` manages backup and commit transactions, and the remaining
modules adapt browser formats and optional data imports. See
[CONTRIBUTING.md](CONTRIBUTING.md) for validation and fixture requirements.

## Known limitations

Arc-specific features and archive UI are not reproduced. Site storage and
IndexedDB, historical download lists, passkeys, and extension settings or vaults
are not automatically transferred. Cookies may not preserve every sign-in.
Extension installation and permissions remain a separate user decision. Zen’s
workspace colours approximate Arc’s appearance.

For supported schemas and operational requirements, consult
[Compatibility](docs/compatibility.md).

## License and acknowledgments

Project code is available under the [MIT License](LICENSE). Runtime components
and format references are documented in [Third-party notices](THIRD_PARTY_NOTICES.md).

[Thinkscape/arc-to-zen](https://github.com/Thinkscape/arc-to-zen) and
[rafcabezas/arc2zen](https://github.com/rafcabezas/arc2zen) informed understanding of
the migration problem and Zen’s session behavior. This project is an independent
implementation, not a fork or wrapper around either repository.
