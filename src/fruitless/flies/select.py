"""Pick neurons out of the pack by MaleCNS annotation.

Model indices are positions in `pack.neuron_ids` (ascending bodyId). Every fly
module describes its circuit as a `Selection` of type patterns and the code here
resolves them against the pack's names sidecar plus the annotation table.

Type names in the release are literal strings with spaces and punctuation
(`Ti flexor MN`, `PEN_a(PEN1)`, `DLMn a, b`). Patterns here are regular
expressions anchored at both ends, so `^JO-A` needs to be written `JO-A.*`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pyarrow as pa

from fruitless.data import annotations as ann


@dataclass(frozen=True)
class Selection:
    """A named group of neurons, described by annotation, resolved lazily."""

    name: str
    types: tuple[str, ...] = ()           # regexes over `type`, fullmatch
    instances: tuple[str, ...] = ()       # exact `instance` values
    classes: tuple[str, ...] = ()         # exact `class` values
    superclasses: tuple[str, ...] = ()    # exact `superclass` values
    side: str | None = None               # "L", "R", "M" against somaSide, else rootSide
    subclass: tuple[str, ...] = ()        # exact `subclass` values
    exclude: tuple[str, ...] = field(default=())  # regexes over `type` to drop

    def mask(self, table: pa.Table) -> np.ndarray:
        n = table.num_rows
        m = np.zeros(n, dtype=bool)
        types = table["type"].to_pylist()
        if self.types:
            rx = [re.compile(p) for p in self.types]
            m |= np.array([t is not None and any(r.fullmatch(t) for r in rx) for t in types])
        if self.instances:
            inst = set(self.instances)
            m |= np.array([v in inst for v in table["instance"].to_pylist()])
        if self.classes:
            cls = set(self.classes)
            m |= np.array([v in cls for v in table["class"].to_pylist()])
        if self.superclasses:
            sc = set(self.superclasses)
            m |= np.array([v in sc for v in table["superclass"].to_pylist()])
        if self.subclass:
            sub = set(self.subclass)
            m &= np.array([v in sub for v in table["subclass"].to_pylist()])
        if self.side is not None:
            soma = table["somaSide"].to_pylist()
            root = table["rootSide"].to_pylist()
            m &= np.array([(s or r) == self.side for s, r in zip(soma, root, strict=True)])
        if self.exclude:
            rx = [re.compile(p) for p in self.exclude]
            m &= ~np.array([t is not None and any(r.fullmatch(t) for r in rx) for t in types])
        return m


class Resolver:
    """Turns Selections into model indices for one pack."""

    def __init__(self, neuron_ids: np.ndarray, table: pa.Table | None = None):
        self.neuron_ids = np.asarray(neuron_ids, dtype=np.int64)
        self.table = ann.neurons(table)
        body = self.table["bodyId"].to_numpy().astype(np.int64)
        order = np.argsort(body, kind="stable")
        at = np.searchsorted(body[order], self.neuron_ids)
        at = np.minimum(at, body.size - 1)
        found = body[order][at] == self.neuron_ids
        if not found.all():
            missing = self.neuron_ids[~found][:5].tolist()
            raise ValueError(f"pack neurons without an annotation row, e.g. {missing}")
        # row in self.table for each model index
        self._row_of_index = order[at]
        # model index for each annotation row (-1 when the row is not in the pack)
        self._index_of_row = np.full(body.size, -1, dtype=np.int64)
        self._index_of_row[self._row_of_index] = np.arange(self.neuron_ids.size)

    def indices(self, sel: Selection) -> np.ndarray:
        rows = np.flatnonzero(sel.mask(self.table))
        idx = self._index_of_row[rows]
        idx = idx[idx >= 0]
        return np.sort(idx).astype(np.int32)

    def resolve(self, sels: dict[str, Selection]) -> dict[str, np.ndarray]:
        return {k: self.indices(s) for k, s in sels.items()}

    def types_of(self, indices: np.ndarray) -> list[str | None]:
        rows = self._row_of_index[np.asarray(indices)]
        return self.table["type"].take(pa.array(rows)).to_pylist()

    def instances_of(self, indices: np.ndarray) -> list[str | None]:
        rows = self._row_of_index[np.asarray(indices)]
        return self.table["instance"].take(pa.array(rows)).to_pylist()


# ---------------------------------------------------------------- shared circuits
# Type names verified against the v1.0 annotation table; see docs/reference.md §2.

EARS = {
    "jo_a": Selection("jo_a", types=(r"JO-A.*",)),
    "jo_b": Selection("jo_b", types=(r"JO-B.*",)),
    "ammc": Selection("ammc", types=(r"AMMC.*",)),
}

ESCAPE = {
    "giant_fiber": Selection("giant_fiber", types=(r"DNp01",)),
    "gfc": Selection("gfc", types=(r"GFC[1-4]",)),
}

MUSHROOM_BODY = {
    "kenyon": Selection("kenyon", classes=("Kenyon_Cell",)),
    "mbon": Selection("mbon", classes=("MBON",)),
    "dan": Selection("dan", classes=("DAN",)),
}
