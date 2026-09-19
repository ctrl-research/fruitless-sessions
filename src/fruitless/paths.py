"""Where things live on disk. Everything under data/ and takes/ is gitignored."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("FRUITLESS_ROOT", Path(__file__).resolve().parents[2]))
DATA = ROOT / "data"
RAW = DATA / "raw" / "male_cns"
PACK = DATA / "pack" / "male_cns_v1"
SOURCES_LOCK = DATA / "sources.lock.json"
TAKES = ROOT / "takes"
TUNES = ROOT / "tunes"
