"""Read the MaleCNS annotation table into something the flies can select from.

Only the columns the project uses are loaded. `bodyId` is the join key to the pack
(`neuron_ids`), `body` in the neurotransmitter table, and `body_pre`/`body_post`
in the weights table. See docs/reference.md section 1 for the value sets.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
import pyarrow as pa
from pyarrow import feather

from fruitless import paths
from fruitless.data.sources import load_lock

COLUMNS = (
    "bodyId", "type", "instance", "superclass", "class", "subclass",
    "somaSide", "rootSide", "status", "fruDsx", "dimorphism", "flywireType",
    "somaNeuromere", "somaLocation",
)


def annotations_path(raw: Path = paths.RAW) -> Path:
    return load_lock()["annotations"].path(raw)


@cache
def load(path: Path | None = None) -> pa.Table:
    return feather.read_table(path or annotations_path(), columns=list(COLUMNS))


def neurons(table: pa.Table | None = None) -> pa.Table:
    """Rows the pack treats as neurons: non-null superclass (166,700 in v1.0)."""
    t = table if table is not None else load()
    keep = np.array([v is not None for v in t["superclass"].to_pylist()], dtype=bool)
    return t.filter(pa.array(keep))


def soma_xyz(table: pa.Table | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(bodyId int64[n], xyz float32[n, 3]) for neurons that have a soma location, in voxels."""
    t = neurons(table)
    loc = t["somaLocation"].to_pylist()
    has = np.array([v is not None and len(v) == 3 for v in loc], dtype=bool)
    ids = t["bodyId"].to_numpy().astype(np.int64)[has]
    xyz = np.array([v for v, h in zip(loc, has, strict=True) if h], dtype=np.float32)
    return ids, xyz
