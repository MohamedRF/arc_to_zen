# Third-party components

arc_to_zen's own code is MIT licensed. The packaged app dynamically links
these independently licensed components; their distribution metadata and license
files are included by the build script.

- **Python** — Python Software Foundation License: <https://docs.python.org/3/license.html>
- **Qt / PySide6 / Shiboken** — LGPLv3/GPLv3 or commercial terms, as applicable:
  <https://doc.qt.io/qtforpython-6/licenses.html>. Source and corresponding Qt
  releases: <https://download.qt.io/official_releases/QtForPython/> and
  <https://download.qt.io/official_releases/qt/>. Qt libraries remain dynamically linked.
- **lz4 / python-lz4** — BSD licensing: <https://github.com/python-lz4/python-lz4>
- **cryptography** — Apache-2.0 or BSD-3-Clause: <https://github.com/pyca/cryptography>
- **PyInstaller** — GPL with the bootloader exception permitting distribution of
  bundled applications: <https://pyinstaller.org/en/stable/license.html>

Mozilla's published Places hashing and session formats informed this independent
implementation. References: <https://github.com/mozilla/gecko-dev/tree/master/toolkit/components/places>
and <https://github.com/mozilla/gecko-dev/blob/master/mfbt/HashFunctions.h>.

Arc and Zen names belong to their respective owners. This project is independent
and is not affiliated with either browser or the reference migration projects.
