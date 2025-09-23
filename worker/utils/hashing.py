import hashlib
from typing import BinaryIO


def compute_sha256_from_stream(stream: BinaryIO) -> str:
    """Compute SHA256 hash from a binary stream."""
    sha256_hash = hashlib.sha256()
    for chunk in iter(lambda: stream.read(8192), b""):
        sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def compute_sha256_from_bytes(data: bytes) -> str:
    """Compute SHA256 hash from bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_from_string(text: str) -> str:
    """Compute SHA256 hash from string."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()