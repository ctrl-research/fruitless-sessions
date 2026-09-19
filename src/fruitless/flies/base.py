"""What a fly is: a role circuit, a drive, and a motor readout.

A `Fly` owns nothing about music. It knows which neurons make up its circuit
(for the hero layer and the page's readout strip), which neurons receive
external drive and how much, and how to turn a grid step's spikes into a small
vector of motor signals. The conductor decides what those signals mean.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fruitless.flies.select import EARS, ESCAPE, Resolver, Selection
from fruitless.sim.constants import TICKS_PER_MS


@dataclass
class Readout:
    """Motor signals for one grid step, all derived from spike counts."""

    names: tuple[str, ...]
    values: np.ndarray   # float32[len(names)]

    def as_dict(self) -> dict[str, float]:
        return {n: float(v) for n, v in zip(self.names, self.values, strict=True)}


@dataclass
class Fly:
    role: str
    circuit: dict[str, Selection]                 # groups shown on the page
    drive: dict[str, Selection]                   # groups that may receive external input
    readout_names: tuple[str, ...]
    mesh_groups: tuple[str, ...] = ()                # groups drawn as meshes on the page
    _idx: dict[str, np.ndarray] = field(default_factory=dict, init=False)
    _drive_idx: dict[str, np.ndarray] = field(default_factory=dict, init=False)

    def resolve(self, r: Resolver, pack=None) -> None:
        """Resolve annotation-based groups. Flies that derive groups from connectivity
        override `derive(r, pack)`, which runs after the annotation groups exist."""
        self._idx = r.resolve({**self.circuit, **EARS, **ESCAPE})
        self._drive_idx = r.resolve(self.drive)
        if pack is not None:
            self.derive(r, pack)

    def derive(self, r: Resolver, pack) -> None:
        """Hook for connectivity-derived groups; default does nothing."""

    @property
    def groups(self) -> dict[str, np.ndarray]:
        return self._idx

    def indices(self, group: str) -> np.ndarray:
        return self._idx[group] if group in self._idx else self._drive_idx[group]

    def add_group(self, name: str, idx: np.ndarray, *, drive: bool = False) -> None:
        idx = np.unique(np.asarray(idx, dtype=np.int32))
        (self._drive_idx if drive else self._idx)[name] = idx

    @staticmethod
    def excitatory_partners(pack, target_idx: np.ndarray, n: int = 60,
                            exclude_superclasses: tuple[str, ...] = ("vnc_motor",),
                            superclass_of=None) -> np.ndarray:
        """The n presynaptic neurons with the largest positive summed weight onto target_idx.

        Derived from the pack's CSR (source-major). Excludes motor neurons so the
        pool is premotor, not the targets themselves.
        """
        rp = np.asarray(pack.row_ptr)
        dst = np.asarray(pack.destinations)
        cnt = np.asarray(pack.signed_counts)
        src = np.repeat(np.arange(pack.n_neurons), np.diff(rp))
        target = np.zeros(pack.n_neurons, dtype=bool)
        target[np.asarray(target_idx)] = True
        m = target[dst]
        wsign = np.bincount(src[m], weights=cnt[m], minlength=pack.n_neurons)
        order = np.argsort(-wsign)
        out = []
        for i in order:
            if wsign[i] <= 0 or len(out) >= n:
                break
            if superclass_of is not None and superclass_of(int(i)) in exclude_superclasses:
                continue
            out.append(int(i))
        return np.array(out, dtype=np.int32)

    def hero_indices(self) -> np.ndarray:
        return np.unique(np.concatenate([*self._idx.values(), *self._drive_idx.values()]))

    def drivable(self) -> np.ndarray:
        """Role drive groups plus the ears: every fly can be played to."""
        ears = [self._idx[k] for k in ("jo_a", "jo_b") if k in self._idx]
        return np.unique(np.concatenate([*self._drive_idx.values(), *ears]))

    def circuit_json(self) -> dict[str, list[int]]:
        return {k: v.tolist() for k, v in self._idx.items()}

    def mesh_indices(self) -> np.ndarray:
        groups = self.mesh_groups or tuple(self._idx)
        return np.unique(np.concatenate([self._idx[g] for g in groups if g in self._idx] or [np.zeros(0, np.int32)]))

    # ------------------------------------------------------------ readout helpers
    @staticmethod
    def rate_hz(counts: np.ndarray, idx: np.ndarray, n_ticks: int) -> float:
        """Mean spikes per neuron per second over a step of n_ticks."""
        if idx.size == 0 or n_ticks == 0:
            return 0.0
        seconds = n_ticks / (1000.0 * TICKS_PER_MS)
        return float(counts[idx].sum()) / idx.size / seconds

    @staticmethod
    def burstiness(events: np.ndarray, idx: np.ndarray, t0: int, n_ticks: int, bin_ms: int = 10) -> float:
        """Coefficient of variation of the group's spike count across bin_ms bins in the step.

        0 for a steady rate, larger when spikes cluster into pulses. This is the
        pulse-versus-sine song classifier: crude, documented, and shown on the page.
        """
        if events.size == 0 or idx.size == 0:
            return 0.0
        mask = np.isin(events[:, 1], idx)
        if not mask.any():
            return 0.0
        b = (events[mask, 0] - t0) // (bin_ms * TICKS_PER_MS)
        n_bins = max(1, -(-n_ticks // (bin_ms * TICKS_PER_MS)))
        hist = np.bincount(b, minlength=n_bins).astype(np.float64)
        m = hist.mean()
        return float(hist.std() / m) if m > 0 else 0.0

    def readout(self, counts: np.ndarray, events: np.ndarray, t0: int, n_ticks: int) -> Readout:
        raise NotImplementedError
