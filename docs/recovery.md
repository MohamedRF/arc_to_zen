# Backups and recovery

Each run lives under the app's private runtime folder and contains:

- `arc-source/`: a full, hash-verified read-only source snapshot.
- `zen-before/`: the complete pre-migration Zen profile.
- `backup-manifest.json`: file sizes and SHA-256 hashes of both backups.
- `report.json`: count-only migration and verification results.
- `recovery.json`: local paths needed for recovery.
- `committed.json`: created only after the verified profile is committed.

A failed stage is retained as `uncommitted-profile/` when possible. It is not
silently substituted for a working profile. If a filesystem failure occurs during
the two directory renames of an update, arc_to_zen restores the previous target name.
Power loss or an OS/process crash is a different failure mode; retain all run and
adjacent `.arc2zen-before-*` directories for manual recovery.

## New-profile mode

The original selected Zen profile was never replaced. Quit Zen and launch the
original profile normally. Keep the generated profile if you might need data
created there. arc_to_zen does not delete either version automatically.

The generated profile is not registered as Zen's default. Use **Open migrated Zen**
in the completed run or launch the recorded path explicitly:

```sh
open -na /Applications/Zen.app --args -profile /path/to/generated/profile
```

## Update-selected-profile mode

1. Quit both browsers completely.
2. Choose **Restore backup…** and the completed replacement run folder.
3. Review and confirm restoration. Backup hashes are checked before use.
4. arc_to_zen retains the current profile in an adjacent `.bridge-replaced-*`
   directory, then restores the full pre-migration profile.

CLI equivalent:

```sh
arc_to_zen restore /path/to/completed-run --yes
```

If a backup was modified, automated restoration refuses it. Do not bypass hash
checks without separately understanding which files changed. Keep a copy of the
current profile before attempting manual recovery. Runtime files, reports, and
backups are private data and must not be committed to this source repository.
