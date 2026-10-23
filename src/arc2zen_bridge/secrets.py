"""Explicit, local-only Keychain access. Secret values never enter reports."""

from __future__ import annotations

import csv
import hashlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .io import readonly_db
from .models import BridgeError
from .paths import all_source_profiles


class ArcKey:
    def __init__(self, storage_password: bytes):
        self._key = hashlib.pbkdf2_hmac("sha1", storage_password, b"saltysalt", 1003, 16)

    @classmethod
    def request(cls) -> ArcKey:
        if sys.platform != "darwin":
            raise BridgeError("Arc Keychain decryption is supported only on macOS.")
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", "Arc Safe Storage", "-w"],
                capture_output=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise BridgeError("Keychain approval timed out. Approve it on your Mac and retry.") from None
        if result.returncode or not result.stdout:
            raise BridgeError("Keychain access was cancelled or denied. No secret values were logged.")
        return cls(result.stdout.removesuffix(b"\n"))

    def decrypt(self, encrypted: bytes, host: str | None = None, cookie_version: int = 0) -> str:
        if not encrypted.startswith(b"v10"):
            raise BridgeError("A credential uses an unsupported encryption format.")
        try:
            decryptor = Cipher(algorithms.AES(self._key), modes.CBC(b" " * 16)).decryptor()
            decoded = decryptor.update(encrypted[3:]) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            decoded = unpadder.update(decoded) + unpadder.finalize()
            if host is not None and cookie_version >= 24:
                if decoded[:32] != hashlib.sha256(host.encode()).digest():
                    raise ValueError("host binding")
                decoded = decoded[32:]
            return decoded.decode("utf-8")
        except (ValueError, UnicodeError):
            raise BridgeError("A credential could not be authenticated or decoded.") from None

    def close(self) -> None:
        # Python cannot promise zeroization of immutable allocations. Do not
        # persist keys, and keep them only for the duration of the operation.
        self._key = b""


def export_passwords(source: Path, destination: Path, key: ArcKey) -> dict:
    records = {}
    counts = Counter()
    # Read/decrypt everything before creating a plaintext output file.
    for profile in all_source_profiles(source):
        for filename in ("Login Data", "Login Data For Account"):
            path = profile / filename
            if not path.exists():
                continue
            with readonly_db(path) as db:
                rows = db.execute(
                    "SELECT origin_url, username_value, CAST(password_value AS BLOB) FROM logins WHERE length(password_value)>0 AND blacklisted_by_user=0"
                )
                for url, username, encrypted in rows:
                    password = key.decrypt(encrypted)
                    counts["source_records"] += 1
                    parsed = urlsplit(url)
                    if parsed.scheme not in ("https", "http") or not parsed.netloc:
                        counts["unsupported_origins"] += 1
                        continue
                    origin = parsed.scheme + "://" + parsed.netloc
                    record_key = (origin, username, password)
                    records[record_key] = {"url": origin, "username": username, "password": password}
    conflicts = Counter((origin, username) for origin, username, _ in records)
    # Native import can overwrite same-origin/same-username differing passwords.
    # Never choose one silently; preserve originals and explain the conflict.
    if any(n > 1 for n in conflicts.values()):
        raise BridgeError(
            "Some profiles contain different passwords for the same site and username. Automatic CSV preparation is blocked; export those profiles separately in Arc."
        )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination.parent, 0o700)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["url", "username", "password"])
            writer.writeheader()
            writer.writerows(records.values())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {
        **counts,
        "distinct_logins": len(records),
        "duplicate_records": counts["source_records"] - counts["unsupported_origins"] - len(records),
    }
