# Contributing

Use a virtual environment and install `.[dev]`. Run pytest, Ruff, and the public-tree
privacy check before submitting changes. Test changes to profile-writing code
against generated fixtures, including commit failure and rollback behavior.

Never add a real browser profile or reproduction export. Extend `demo.py` or the
test factories with fictional `example.test` URLs, names, and credentials. The
`--demo` GUI intentionally disables migration and never scans a real profile.

Do not add logging of URLs, titles, cookie/login values, or raw database exception
messages. Do not silently weaken browser security or auto-approve Keychain/extension
permissions. Document any new unsupported data type or skipped-record count.

Keep format adapters small and separate from the transaction boundary. Migration
must stage, verify, and retain recoverable originals before committing a result.
