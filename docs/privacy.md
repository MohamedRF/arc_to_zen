# Privacy and data handling

The application has no upload client, telemetry, analytics, account, or background
update check. All migration operations are local. Opening Zen can of course let
Zen visit and synchronize sites according to the user's existing settings.

The repository includes only implementation code, documentation, an original
vector icon, and fictional fixture code / screenshots. It must never contain a
real sidebar, profile, database, password export, report, cookie, username, email,
or browsing-history sample. `.gitignore` excludes browser file types, and
`scripts/check_public_tree.py` checks tracked files for common leak patterns.
That checker is a guardrail, not a substitute for reviewing files and images.

## Local run folders contain private data

Backups contain full browser profiles. A runtime folder and its run folders are
owner-only; copied profile files remain under that restricted directory. The
normal report includes counts, option flags, and generic limitations, without
URLs, tab titles, space names, login names, passwords, or cookie values. Recovery
metadata contains local filesystem paths because restoration needs them. Do not
share an entire run folder when filing an issue.

The app refuses to put runtime browser data under a Git repository or inside
either input browser folder. It rejects browser-folder symlinks and unsafe profile
names. Source databases are never opened for writing.

## Authentication

Keychain access is requested only after opting into cookies or explicitly
preparing a password CSV. Enter any required macOS authentication directly in
macOS's prompt. Bridge never asks you to type a Mac password into the app.
Credential values do not enter progress logs or exception messages.

The temporary CSV is plaintext by necessity for native Zen import. Delete it after
checking the import. Do not open it in a spreadsheet or upload it to a bug report.
Protect and eventually remove backups according to your own retention policy.

## Reporting a problem

Start with browser versions, the generic error message, and fictional reproduction
steps. Do not post raw profiles, tab names/URLs, Keychain contents, screenshots
of private browser data, or credential exports to a public issue.
