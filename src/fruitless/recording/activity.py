"""Binned activity in the take-bundle format the stage reads.

One layer of activity is a directory:

    activity.json            {"format": "fsa1", "bin_ms", "chunk_s", "n_bins", "n_chunks",
                              "n_neurons", "space": "pack" | "subset", "subset": "subset.npy"?}
    chunk_0000.bin ...       one file per chunk_s seconds of biological time
    subset.npy               int32 model indices when space == "subset" (the hero layer)

Each chunk file, little-endian:

    magic      4 bytes  b"FSA1"
    bin_ms     uint32
    n_bins     uint32   bins in this chunk
    n_neurons  uint32   size of the index space
    n_events   uint32
    offsets    uint32[n_bins + 1]   event range of each bin
    neuron     uint32[n_events]     index in the layer's space
    count      uint8[n_events]      spikes of that neuron in that bin, saturating at 255

Events within a bin are sorted by neuron. A neuron that did not fire in a bin
has no event, which is what keeps whole-brain layers small: most of a LIF
connectome is silent most of the time.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fruitless.sim.constants import TICKS_PER_MS

MAGIC = b"FSA1"
_HEADER = struct.Struct("<4sIIII")


@dataclass
class Chunk:
    bin_ms: int
    n_neurons: int
    offsets: np.ndarray   # uint32[n_bins + 1]
    neuron: np.ndarray    # uint32[n_events]
    count: np.ndarray     # uint8[n_events]

    @property
    def n_bins(self) -> int:
        return int(self.offsets.size - 1)

    def bin(self, b: int) -> tuple[np.ndarray, np.ndarray]:
        lo, hi = int(self.offsets[b]), int(self.offsets[b + 1])
        return self.neuron[lo:hi], self.count[lo:hi]

    def dense(self) -> np.ndarray:
        """uint8[n_bins, n_neurons]; for tests and small layers only."""
        out = np.zeros((self.n_bins, self.n_neurons), dtype=np.uint8)
        for b in range(self.n_bins):
            n, c = self.bin(b)
            out[b, n] = c
        return out


def write_chunk(path: Path, chunk: Chunk) -> None:
    if chunk.offsets.dtype != np.uint32 or chunk.neuron.dtype != np.uint32 \
            or chunk.count.dtype != np.uint8:
        raise ValueError("chunk arrays must be uint32 offsets, uint32 neuron, uint8 count")
    with path.open("wb") as fh:
        fh.write(_HEADER.pack(MAGIC, chunk.bin_ms, chunk.n_bins, chunk.n_neurons,
                              int(chunk.neuron.size)))
        fh.write(chunk.offsets.astype("<u4").tobytes())
        fh.write(chunk.neuron.astype("<u4").tobytes())
        fh.write(chunk.count.tobytes())


def read_chunk(path: Path) -> Chunk:
    data = Path(path).read_bytes()
    magic, bin_ms, n_bins, n_neurons, n_events = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"{path}: not an FSA1 chunk")
    o = _HEADER.size
    offsets = np.frombuffer(data, dtype="<u4", count=n_bins + 1, offset=o).astype(np.uint32)
    o += 4 * (n_bins + 1)
    neuron = np.frombuffer(data, dtype="<u4", count=n_events, offset=o).astype(np.uint32)
    o += 4 * n_events
    count = np.frombuffer(data, dtype=np.uint8, count=n_events, offset=o).copy()
    return Chunk(bin_ms, n_neurons, offsets, neuron, count)


def bin_events(events: np.ndarray, t0_tick: int, n_bins: int, bin_ms: int,
               n_neurons: int, remap: np.ndarray | None = None) -> Chunk:
    """Bin (tick, neuron) events that fall in [t0_tick, t0_tick + n_bins * bin_ticks).

    remap: int32[pack N] giving each pack index its position in the layer's
    space, or -1 to drop it. None means the layer's space is the pack's.
    """
    bin_ticks = bin_ms * TICKS_PER_MS
    ev = np.asarray(events)
    if ev.size == 0:
        return Chunk(bin_ms, n_neurons, np.zeros(n_bins + 1, np.uint32),
                     np.zeros(0, np.uint32), np.zeros(0, np.uint8))
    tick = ev[:, 0].astype(np.int64) - t0_tick
    neuron = ev[:, 1].astype(np.int64)
    inside = (tick >= 0) & (tick < n_bins * bin_ticks)
    tick, neuron = tick[inside], neuron[inside]
    if remap is not None:
        neuron = remap[neuron]
        keep = neuron >= 0
        tick, neuron = tick[keep], neuron[keep]
    b = tick // bin_ticks
    key = b * n_neurons + neuron
    uniq, cnt = np.unique(key, return_counts=True)
    bins = uniq // n_neurons
    offsets = np.zeros(n_bins + 1, dtype=np.uint32)
    np.cumsum(np.bincount(bins, minlength=n_bins), out=offsets[1:])
    return Chunk(bin_ms, n_neurons, offsets,
                 (uniq % n_neurons).astype(np.uint32),
                 np.minimum(cnt, 255).astype(np.uint8))


@dataclass
class ActivityWriter:
    """Accumulates (tick, neuron) events from Session steps and writes chunk files."""

    directory: Path
    bin_ms: int
    chunk_s: float
    n_neurons_pack: int
    subset: np.ndarray | None = None      # int32 model indices for a hero layer
    _remap: np.ndarray | None = field(default=None, init=False)
    _pending: list[np.ndarray] = field(default_factory=list, init=False)
    _next_chunk: int = field(default=0, init=False)
    _ticks_seen: int = field(default=0, init=False)

    def __post_init__(self):
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.subset is not None:
            self.subset = np.asarray(self.subset, dtype=np.int32)
            self._remap = np.full(self.n_neurons_pack, -1, dtype=np.int64)
            self._remap[self.subset] = np.arange(self.subset.size)
            np.save(self.directory / "subset.npy", self.subset)
        self.chunk_ticks = round(self.chunk_s * 1000) * TICKS_PER_MS
        if self.chunk_ticks % (self.bin_ms * TICKS_PER_MS):
            raise ValueError("chunk_s must be a whole number of bins")
        self.bins_per_chunk = self.chunk_ticks // (self.bin_ms * TICKS_PER_MS)

    @property
    def n_neurons(self) -> int:
        return int(self.subset.size) if self.subset is not None else self.n_neurons_pack

    def add(self, events: np.ndarray, n_ticks: int) -> None:
        """Events of the step just run, and how many ticks it spanned."""
        if events.size:
            self._pending.append(np.asarray(events, dtype=np.int64))
        self._ticks_seen += n_ticks
        while self._ticks_seen >= (self._next_chunk + 1) * self.chunk_ticks:
            self._flush_chunk()

    def _flush_chunk(self, partial_bins: int | None = None) -> None:
        t0 = self._next_chunk * self.chunk_ticks
        n_bins = partial_bins if partial_bins is not None else self.bins_per_chunk
        ev = np.concatenate(self._pending) if self._pending else np.zeros((0, 2), np.int64)
        chunk = bin_events(ev, t0, n_bins, self.bin_ms, self.n_neurons, self._remap)
        write_chunk(self.directory / f"chunk_{self._next_chunk:04d}.bin", chunk)
        # keep only events beyond this chunk
        if ev.size:
            later = ev[ev[:, 0] >= t0 + self.chunk_ticks]
            self._pending = [later] if later.size else []
        self._next_chunk += 1

    def close(self) -> dict:
        remainder = self._ticks_seen - self._next_chunk * self.chunk_ticks
        if remainder > 0:
            bin_ticks = self.bin_ms * TICKS_PER_MS
            self._flush_chunk(partial_bins=-(-remainder // bin_ticks))
        n_bins = -(-self._ticks_seen // (self.bin_ms * TICKS_PER_MS))
        meta = {
            "format": "fsa1",
            "bin_ms": self.bin_ms,
            "chunk_s": self.chunk_s,
            "n_bins": int(n_bins),
            "n_chunks": self._next_chunk,
            "n_neurons": self.n_neurons,
            "space": "subset" if self.subset is not None else "pack",
            "ticks": int(self._ticks_seen),
            "dt_ms": 1.0 / TICKS_PER_MS,
        }
        if self.subset is not None:
            meta["subset"] = "subset.npy"
        (self.directory / "activity.json").write_text(json.dumps(meta, indent=2) + "\n")
        return meta
