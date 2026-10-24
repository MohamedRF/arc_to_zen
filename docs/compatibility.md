# Compatibility and verification

The app targets macOS 14+ and the modern Arc macOS sidebar / Zen dual-session
layout. It checks file structure rather than assuming every future browser
version is compatible. Automated coverage uses generated fixtures; compatibility with every real
profile or future browser version is not guaranteed.

## Input requirements

- Arc root containing `StorableSidebar.json` and, for standard-data imports,
  `User Data/<profile>/...`.
- Zen profile containing `zen-sessions.jsonlz4` with spaces/tabs/folders/groups
  arrays, and `sessionstore.jsonlz4` with a saved normal window.
- Both browsers completely quit for any write or recovery operation. arc_to_zen does
  not terminate processes or discard an active browser session.
- Enough free space for full Arc and Zen backups, staging, and the result.

Browser runtime markers (`SingletonSocket`, `SingletonCookie`, `SingletonLock`,
`RunningChromeVersion`, `.parentlock`, `parent.lock`, and `lock`) and `.DS_Store`
are excluded from backups and file manifests. These markers may be dangling
symlinks after a browser exits; they are neither followed nor copied. Other
browser-folder symlinks still block migration.

Arc's alternating key/value lists, variable pinned/unpinned marker order, empty
spaces, Essentials-only spaces, and unused profile Essentials are handled.
Two spaces with the same name retain different IDs. Spaces sharing one Arc profile
share one Zen container and one set of Essentials, as in Arc.

Unknown or missing sidebar structure blocks migration. Tabs without saved URLs
and unavailable favicons are reported as counts; unsupported structures are never
quietly declared a complete copy. Folder collapsed state is read when present in
the supported sidebar list data; otherwise folders start collapsed. Historical
Arc live-state formats and arbitrary custom folder styling are not interpreted.

## Verification boundary

Before commit, the app compares every extracted tab's URL, pinned/Essential
state, workspace ID, and full folder path. It checks workspace ordering, names,
emoji, profile containers, and matching tab IDs in both Zen session files. Session
compression is round-tripped before replacement. SQLite integrity checks run on
modified standard-data databases, with Places foreign-key/hash checks.

This is **on-disk verification**. Only Zen itself can confirm that a future
version restores its UI correctly. Restart Zen and review important workspaces,
folders, sites, and accounts before removing Arc or backups.

## Standard data

- SQLite readers use read-only connections and account for WAL state.
- History converts Chromium timestamps, keeps supported visit types, and dedups
  by URL/time/type. Browser-internal and invalid URLs are excluded and counted.
  Zen's Places history is shared across its containers; it does not retain Arc's
  separate per-profile history interfaces.
- Existing Zen workspaces, tabs, bookmarks, cookies, and closed-tab state are
  retained. Regular bookmarks are added to an import folder. Unchanged bookmark
  files are not imported again; changed snapshots may produce a new import folder
  to avoid deleting user-edited bookmarks from the previous import.
- Form history requires an initialized, supported `moz_formhistory` database.
  Disable that option if the target has never created form history.
- Cached PNG/ICO favicons are best-effort and limited in size.

## Passwords and cookies

Only macOS Arc Safe Storage `v10` encryption is supported. The Keychain secret is
captured in memory, never printed, stored in a report, or passed as a command-line
argument. Python cannot guarantee zeroization of immutable memory allocations;
keys are retained only for the current operation.

Password CSV preparation is an explicit post-migration action. Native Zen import
is required and must be checked by the user. Unsupported crypto or conflicting
same-origin/username passwords blocks preparation. CSV permissions are `0600` in
a `0700` directory. App exit reminds the user if the CSV remains; it does not claim
secure erasure on SSDs, undo cloud sync, or manage third-party password vaults.

Cookies are off by default. If enabled, the app checks Chromium's host-bound
cookie prefix, preserves security/HTTP-only/SameSite/scheme/expiry attributes, and
maps them into the original profile's container. Session cookies remain session
cookies in Firefox's restore data. Existing target cookies are not overwritten.
Expired, partitioned, and unsupported-attribute cookies are counted and excluded.
Moving cookies is not a guarantee that a site will accept the session.

## Deliberately separate

Passkeys, extension installation/permissions and data, site local storage,
IndexedDB, Service Worker state, Downloads UI, Arc archives/Boosts/Easels, and
browser sync accounts are not transplanted. Full Arc backups retain the original
files. No browser security setting is disabled to make a migration work.
