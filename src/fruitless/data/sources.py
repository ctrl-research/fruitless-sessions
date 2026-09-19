"""The three MaleCNS v1.0 release tables: fetch, verify, and refuse to proceed on a mismatch.

The lock file `data/sources.lock.json` records name, size and SHA-256 of each
table as downloaded on 2026-09-18. A take manifest copies these hashes, so a
take says exactly which bytes it was computed from.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fruitless import paths


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    bytes: int
    sha256: str
    url: str

    def path(self, raw: Path = paths.RAW) -> Path:
        return raw / self.name


def load_lock(lock: Path = paths.SOURCES_LOCK) -> dict[str, Source]:
    doc = json.loads(lock.read_text())
    return {
        key: Source(key, f["name"], int(f["bytes"]), f["sha256"], doc["base_url"] + f["name"])
        for key, f in doc["files"].items()
    }


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def verify(source: Source, raw: Path = paths.RAW, *, hash_check: bool = True) -> bool:
    """True when the file is present with the locked size (and hash, unless skipped)."""
    p = source.path(raw)
    if not p.is_file() or p.stat().st_size != source.bytes:
        return False
    return not hash_check or sha256_file(p) == source.sha256


def fetch(source: Source, raw: Path = paths.RAW) -> Path:
    """Download with curl (resumable), then verify. Raises on a hash mismatch."""
    if shutil.which("curl") is None:
        raise RuntimeError("curl is required to fetch the release tables")
    raw.mkdir(parents=True, exist_ok=True)
    out = source.path(raw)
    if verify(source, raw, hash_check=False):
        pass
    else:
        subprocess.run(
            ["curl", "-fL", "--retry", "10", "--retry-all-errors", "--retry-delay", "5",
             "-C", "-", "-o", str(out), source.url],
            check=True,
        )
    if not verify(source, raw):
        raise RuntimeError(
            f"{out} does not match sources.lock.json (expected sha256 {source.sha256}); "
            "the release may have changed, do not proceed without updating the lock deliberately"
        )
    return out


def fetch_all(raw: Path = paths.RAW, lock: Path = paths.SOURCES_LOCK) -> dict[str, Path]:
    sources = load_lock(lock)
    got = {}
    for key, src in sources.items():
        print(f"{key:18s} {src.name}", file=sys.stderr)
        got[key] = fetch(src, raw)
    return got
