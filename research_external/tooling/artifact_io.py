"""Write/reopen/hash primitives for research_external/. No trading logic, no
optimization, no MT5 connection here -- pure file I/O and hashing, deliberately kept
this narrow so it can never be a second candidate-admission or validation authority.

Hash rule: sha256_of_file() always reads bytes fresh from disk -- it never hashes an
in-memory buffer before a write. This is the one thing every artifact in this
workspace is required to prove (write, close, reopen, hash twice, compare).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

import pandas as pd

_HEX64 = frozenset("0123456789abcdef")


def sha256_of_file(path: str) -> str:
    """Reads the file fresh from disk in binary mode and returns its SHA-256 as a
    64-character lowercase hex digest -- never derived from an in-memory buffer."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    assert len(digest) == 64 and set(digest) <= _HEX64, f"malformed digest for {path!r}: {digest!r}"
    return digest


@dataclass(frozen=True)
class WrittenArtifact:
    path: str
    size_bytes: int
    sha256_pass1: str
    sha256_pass2: str

    @property
    def reproducible(self) -> bool:
        return self.sha256_pass1 == self.sha256_pass2


def _verify_reproducible(path: str) -> WrittenArtifact:
    """Common close/reopen/hash-twice verification every writer below performs."""
    size = os.path.getsize(path)
    pass1 = sha256_of_file(path)
    pass2 = sha256_of_file(path)
    return WrittenArtifact(path=path, size_bytes=size, sha256_pass1=pass1, sha256_pass2=pass2)


def write_csv(path: str, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> WrittenArtifact:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return _verify_reproducible(path)


def read_csv(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_parquet(path: str, rows: Sequence[Mapping[str, Any]]) -> WrittenArtifact:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame = pd.DataFrame(list(rows))
    frame.to_parquet(path, engine="pyarrow", index=False)
    return _verify_reproducible(path)


def read_parquet(path: str) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def write_json_manifest(path: str, payload: Mapping[str, Any]) -> WrittenArtifact:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, indent=2, default=str)
    with open(path, "wb") as fh:
        fh.write(serialized.encode("utf-8"))
    return _verify_reproducible(path)
