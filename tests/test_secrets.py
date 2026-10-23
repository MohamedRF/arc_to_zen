import hashlib
import sqlite3
import stat
import time

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from arc_to_zen.arc import extract
from arc_to_zen.cookies import import_cookies
from arc_to_zen.io import read_session
from arc_to_zen.models import BridgeError
from arc_to_zen.secrets import ArcKey, export_passwords
from arc_to_zen.standard import CHROME_EPOCH
from arc_to_zen.zen import import_sidebar


def encrypted(key, raw):
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key._key), modes.CBC(b" " * 16)).encryptor()
    return b"v10" + encryptor.update(padded) + encryptor.finalize()


def test_password_origin_dedup_private_permissions_and_no_logs(demo_paths, tmp_path, capsys):
    arc, _ = demo_paths
    key = ArcKey(b"fictional-key-for-unit-tests")
    value = encrypted(key, b"fictional-secret-not-an-account")
    with sqlite3.connect(arc / "User Data/Default/Login Data") as db:
        db.executemany(
            "INSERT INTO logins VALUES(?,?,?,0)",
            [
                ("https://example.test/a", "fictional-user", value),
                ("https://example.test/b", "fictional-user", value),
            ],
        )
    path = tmp_path / "private/passwords.csv"
    result = export_passwords(arc, path, key)
    assert result["distinct_logins"] == 1
    assert result["duplicate_records"] == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert capsys.readouterr().out == ""
    assert "fictional-secret" not in repr(result)


def test_conflicting_passwords_block_output(demo_paths, tmp_path):
    arc, _ = demo_paths
    key = ArcKey(b"fictional-key-for-unit-tests")
    with sqlite3.connect(arc / "User Data/Default/Login Data") as db:
        for password in (b"fictional-one", b"fictional-two"):
            db.execute(
                "INSERT INTO logins VALUES('https://example.test/a','same-fictional-user',?,0)",
                (encrypted(key, password),),
            )
    path = tmp_path / "private/passwords.csv"
    with pytest.raises(BridgeError, match="different passwords"):
        export_passwords(arc, path, key)
    assert not path.exists()


def test_unsupported_crypto_never_creates_plaintext_file(demo_paths, tmp_path):
    arc, _ = demo_paths
    with sqlite3.connect(arc / "User Data/Default/Login Data") as db:
        db.execute("INSERT INTO logins VALUES('https://example.test','fictional',?,0)", (b"v99-unsupported",))
    path = tmp_path / "private/passwords.csv"
    with pytest.raises(BridgeError, match="unsupported encryption"):
        export_passwords(arc, path, ArcKey(b"fictional-key"))
    assert not path.exists()


def cookie_fixture(path, key, wrong_host=False):
    now = int(time.time())
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE meta(key TEXT,value TEXT); INSERT INTO meta VALUES('version','24'); CREATE TABLE cookies(host_key TEXT,name TEXT,value TEXT,encrypted_value TEXT,path TEXT,expires_utc INTEGER,is_persistent INTEGER,is_secure INTEGER,is_httponly INTEGER,last_access_utc INTEGER,creation_utc INTEGER,samesite INTEGER,source_scheme INTEGER,top_frame_site_key TEXT);"
        )
        for name, persistent, expiry, partition in [
            ("saved", 1, now + 3600, ""),
            ("session", 0, 0, ""),
            ("old", 1, now - 1, ""),
            ("partition", 1, now + 3600, "https://top.example.test"),
        ]:
            digest = hashlib.sha256(
                ("wrong.example.test" if wrong_host else ".example.test").encode()
            ).digest()
            value = encrypted(key, digest + b"fictional-cookie-value")
            # Real older Arc databases can have arbitrary encrypted bytes in TEXT.
            db.execute(
                "INSERT INTO cookies VALUES(?,?,?,CAST(? AS TEXT),'/',?,?,?,?,?,?,1,2,?)",
                (
                    ".example.test",
                    name,
                    "",
                    value,
                    CHROME_EPOCH + expiry * 1_000_000,
                    persistent,
                    1,
                    1,
                    CHROME_EPOCH + now * 1_000_000,
                    CHROME_EPOCH + now * 1_000_000,
                    partition,
                ),
            )


def test_cookie_text_blob_host_binding_expiry_partition_and_context(demo_paths):
    arc, zen = demo_paths
    key = ArcKey(b"fictional-cookie-key")
    cookie_fixture(arc / "User Data/Default/Cookies", key)
    contexts = import_sidebar(zen, extract(arc))
    result = import_cookies(arc, zen, contexts, key)
    assert result == {
        "persistent_cookies": 1,
        "session_cookies": 1,
        "expired_cookies_skipped": 1,
        "partitioned_cookies_skipped": 1,
    }
    with sqlite3.connect(zen / "cookies.sqlite") as db:
        assert (
            db.execute("SELECT originAttributes FROM moz_cookies").fetchone()[0]
            == f"^userContextId={contexts['Default']}"
        )
    for name in ("sessionstore.jsonlz4", "sessionstore-backups/recovery.jsonlz4"):
        cookie = read_session(zen / name)["cookies"][0]
        assert cookie["originAttributes"] == {"userContextId": contexts["Default"]}
        assert "expiry" not in cookie  # Session cookies never become persistent.


def test_cookie_host_authentication_failure_rolls_back(demo_paths):
    arc, zen = demo_paths
    key = ArcKey(b"fictional-cookie-key")
    cookie_fixture(arc / "User Data/Default/Cookies", key, wrong_host=True)
    contexts = import_sidebar(zen, extract(arc))
    with pytest.raises(BridgeError, match="authenticated"):
        import_cookies(arc, zen, contexts, key)
    with sqlite3.connect(zen / "cookies.sqlite") as db:
        assert db.execute("SELECT COUNT(*) FROM moz_cookies").fetchone()[0] == 0
