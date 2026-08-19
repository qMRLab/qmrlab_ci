import hashlib

import pytest

from scripts.fetch_data import ChecksumError, verify


def test_matching_checksum_and_size_passes(tmp_path):
    p = tmp_path / "a.zip"
    p.write_bytes(b"payload")

    verify(p, hashlib.sha256(b"payload").hexdigest(), 7)


def test_wrong_checksum_raises(tmp_path):
    p = tmp_path / "a.zip"
    p.write_bytes(b"payload")

    with pytest.raises(ChecksumError, match="sha256"):
        verify(p, "0" * 64, 7)


def test_right_checksum_wrong_size_still_raises(tmp_path):
    """Both are declared, so both are checked; a size mismatch means the pin is stale."""
    p = tmp_path / "a.zip"
    p.write_bytes(b"payload")

    with pytest.raises(ChecksumError, match="bytes"):
        verify(p, hashlib.sha256(b"payload").hexdigest(), 999)
