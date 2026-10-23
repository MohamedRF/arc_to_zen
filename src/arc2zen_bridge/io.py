from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import lz4.block

from .models import BridgeError

MAX_SESSION_BYTES = 256 * 1024 * 1024


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".bridge-tmp")
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, indent=2).encode())


def read_session(path: Path) -> dict:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:8] != b"mozLz40\0":
        raise BridgeError("A Zen session file has an unsupported format.")
    size = int.from_bytes(raw[8:12], "little")
    if size > MAX_SESSION_BYTES:
        raise BridgeError("A Zen session exceeds the supported size limit.")
    decoded = lz4.block.decompress(raw[8:])
    if len(decoded) != size:
        raise BridgeError("A Zen session failed its length check.")
    value = json.loads(decoded)
    if not isinstance(value, dict):
        raise BridgeError("A Zen session does not contain an object.")
    return value


def write_session(path: Path, value: dict) -> None:
    decoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if len(decoded) > MAX_SESSION_BYTES:
        raise BridgeError("The generated session exceeds the supported size limit.")
    encoded = b"mozLz40\0" + lz4.block.compress(decoded, store_size=True)
    if json.loads(lz4.block.decompress(encoded[8:])) != value:
        raise BridgeError("The generated session failed round-trip validation.")
    atomic_bytes(path, encoded)


def readonly_db(path: Path) -> sqlite3.Connection:
    # Do not use immutable=1: a closed browser can still have a valid WAL.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def has_table(db: sqlite3.Connection, table: str) -> bool:
    return (
        db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        is not None
    )


def integrity(path: Path) -> None:
    with readonly_db(path) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BridgeError("A browser database failed its integrity check.")


def backup_database(source: Path, destination: Path) -> None:
    with readonly_db(source) as src, sqlite3.connect(destination) as dest:
        src.backup(dest)
