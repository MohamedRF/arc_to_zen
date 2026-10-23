import pytest

from arc_to_zen.io import atomic_bytes, read_session, write_session
from arc_to_zen.models import BridgeError


def test_session_round_trip_and_bad_header(tmp_path):
    p = tmp_path / "test.jsonlz4"
    data = {"spaces": [{"name": "Fictional 🔬"}], "tabs": []}
    write_session(p, data)
    assert read_session(p) == data
    p.write_bytes(b"not-a-session")
    with pytest.raises(BridgeError, match="unsupported format"):
        read_session(p)


def test_oversized_session_rejected_before_decompression(tmp_path):
    p = tmp_path / "test.jsonlz4"
    p.write_bytes(b"mozLz40\0" + (300 * 1024 * 1024).to_bytes(4, "little") + b"invalid")
    with pytest.raises(BridgeError, match="size limit"):
        read_session(p)


def test_atomic_writer_refuses_existing_temp_file(tmp_path):
    target = tmp_path / "prefs.js"
    target.write_bytes(b"original")
    temporary = tmp_path / "prefs.js.bridge-tmp"
    temporary.write_bytes(b"do not follow")
    with pytest.raises(FileExistsError):
        atomic_bytes(target, b"new")
    assert target.read_bytes() == b"original"
    assert temporary.read_bytes() == b"do not follow"
