"""A stateful run of the MLX engine, advanced one segment at a time.

`lif.engine_fused.run` simulates one fixed stimulus from a fresh state. The
ensemble needs the opposite: every fly keeps its membrane state between grid
steps, and the input for the next step is decided from what the other flies
just did. This wraps the engine's two Metal kernels in a `Session` object whose
`step()` takes the external drive for the next T ticks and returns the spikes
they produced.

Tick semantics, constants and kernel order are the engine's, so a Session that
is stepped through the same total draws as one `run()` produces the same spike
train. `tests/test_session.py` checks that on a small subnetwork.
"""

from __future__ import annotations

from dataclasses import dataclass

import mlx.core as mx
import numpy as np
from lif import core, spike_record
from lif.engine_fused import _state_kernel
from lif.engine_metal import propagate, silenced_row_end

from fruitless.sim.constants import DT_MS, TICKS_PER_MS

if abs(DT_MS - core.DT) > 1e-12 or TICKS_PER_MS != round(1.0 / core.DT):
    raise ImportError(f"fruitless.sim.constants disagrees with the engine's dt {core.DT} ms")


@dataclass
class StepResult:
    t0: int                   # first tick of this step (absolute)
    n_ticks: int
    events: np.ndarray        # int32[E, 2] of (absolute tick, neuron), sorted
    counts: np.ndarray        # int32[N], spikes per neuron in this step


class Session:
    """One fly's brain, live on the GPU, advanced by `step()`.

    drivable: model indices that may ever receive external input. As in the
    published model these neurons have no refractory period. The set is fixed
    for the life of the session; drive any subset of it on any step by passing
    zeros for the rest.
    """

    def __init__(self, pack: core.Pack, drivable: np.ndarray,
                 silenced: np.ndarray | None = None, edge_split: int = 1,
                 chunk: int = 32, cap: int = spike_record.CAP):
        drivable = np.asarray(drivable)
        if drivable.ndim != 1 or not np.issubdtype(drivable.dtype, np.integer):
            raise ValueError("drivable must be a 1-D integer array of model indices")
        if np.unique(drivable).size != drivable.size:
            raise ValueError("drivable lists a neuron more than once")
        if drivable.size and (drivable.min() < 0 or drivable.max() >= pack.n_neurons):
            raise ValueError("drivable index out of range")
        if chunk < 1:
            raise ValueError("chunk must be at least 1")

        self.pack = pack
        self.drivable = np.sort(drivable).astype(np.int32)
        self.chunk = chunk
        self.edge_split = edge_split
        self.N = pack.n_neurons
        self.t = 0

        self._row_end = silenced_row_end(pack, core.silenced_mask(pack, silenced))
        cf = core.constants_f32()
        self._k = {f"c_{name}": mx.array([float(cf[name])], dtype=mx.float32)
                   for name in ("v0_term", "couple_g", "decay_v", "decay_g", "v_th",
                                "w_syn", "w_ext", "v_0")}
        self._n_neurons = mx.array([self.N], dtype=mx.uint32)
        self._n_src = mx.array([self.N], dtype=mx.uint32)

        slot = np.full(self.N, -1, dtype=np.int32)
        slot[self.drivable] = np.arange(self.drivable.size, dtype=np.int32)
        self._target_slot = mx.array(slot)

        rfc_reload = np.full(self.N, core.RFC_TICKS, dtype=np.int32)
        rfc_reload[self.drivable] = 0
        self._rfc_reload = mx.array(rfc_reload)

        self.v = mx.full((self.N,), core.V_0, dtype=mx.float32)
        self.g = mx.zeros((self.N,), dtype=mx.float32)
        self.rfc = mx.zeros((self.N,), dtype=mx.int32)
        self.counts = mx.zeros((self.N,), dtype=mx.int32)
        self.ring = [mx.zeros((self.N,), dtype=mx.uint8) for _ in range(core.DELAY_TICKS)]
        mx.eval(self.v, self.g, self.rfc, self.counts, *self.ring)
        self._cap = cap

    # ------------------------------------------------------------------ stepping
    def step(self, draws: np.ndarray) -> StepResult:
        """Advance by draws.shape[0] ticks. draws is bool[T, len(drivable)]."""
        draws = np.asarray(draws)
        if draws.ndim != 2 or draws.shape[1] != self.drivable.size:
            raise ValueError(f"draws must be [T, {self.drivable.size}], got {draws.shape}")
        T = draws.shape[0]
        if T == 0:
            return StepResult(self.t, 0, np.zeros((0, 2), np.int32), np.zeros(self.N, np.int32))
        draws_u8 = mx.array(draws.astype(np.uint8))

        rec = spike_record.Recorder(self.N, self._cap)
        counts_before = self.counts
        t_local = 0
        while t_local < T:
            kk = min(self.chunk, T - t_local)
            spikes = []
            for i in range(kk):
                t_abs = self.t + t_local + i
                s = t_abs % core.DELAY_TICKS
                contrib = propagate(self.ring[s], self.pack, self._n_src, self.edge_split,
                                    row_end=self._row_end)
                self.v, self.g, self.rfc, self.counts, spike = _state_kernel(
                    inputs=[self.v, self.g, self.rfc, self.counts, contrib,
                            draws_u8[t_local + i], self._target_slot, self._rfc_reload,
                            self._n_neurons, self._k["c_v0_term"], self._k["c_couple_g"],
                            self._k["c_decay_v"], self._k["c_decay_g"], self._k["c_v_th"],
                            self._k["c_w_syn"], self._k["c_w_ext"], self._k["c_v_0"]],
                    output_shapes=[(self.N,)] * 5,
                    output_dtypes=[mx.float32, mx.float32, mx.int32, mx.int32, mx.uint8],
                    grid=(self.N, 1, 1),
                    threadgroup=(256, 1, 1),
                )
                self.ring[s] = spike
                spikes.append(spike)
            out = rec.submit(spikes, self.t + t_local)
            mx.async_eval(self.v, self.g, self.rfc, self.counts, *self.ring, *out)
            rec.drain(keep=1)
            t_local += kk
        mx.eval(self.v, self.g, self.rfc, self.counts, *self.ring)
        events = rec.events()
        step_counts = np.asarray(self.counts) - np.asarray(counts_before)
        result = StepResult(self.t, T, events, step_counts.astype(np.int32))
        self.t += T
        return result

    # ------------------------------------------------------------------ helpers
    def zero_draws(self, n_ticks: int) -> np.ndarray:
        return np.zeros((n_ticks, self.drivable.size), dtype=bool)

    def total_counts(self) -> np.ndarray:
        return np.asarray(self.counts)


def poisson_draws(rates_hz: np.ndarray, ticks_per_bin: int, rng: np.random.Generator) -> np.ndarray:
    """Bernoulli-per-tick draws from a rate that is piecewise constant per bin.

    rates_hz: float[B, K], one rate per bin per drivable neuron. Returns
    bool[B * ticks_per_bin, K]. As in `core.make_stimulus_for`, a rate of r Hz is
    a per-tick probability of r * dt / 1000.
    """
    rates = np.asarray(rates_hz, dtype=np.float64)
    if rates.ndim != 2:
        raise ValueError("rates_hz must be [bins, neurons]")
    p = rates * (DT_MS / 1000.0)
    if (p < 0).any() or (p > 1).any():
        raise ValueError(f"rates must be within 0 to {1000.0 / DT_MS:g} Hz")
    p_ticks = np.repeat(p, ticks_per_bin, axis=0)
    return rng.random(p_ticks.shape) < p_ticks


def constant_drive(session: Session, targets: np.ndarray, rate_hz: float, n_ticks: int,
                   rng: np.random.Generator) -> np.ndarray:
    """draws for `session` with `targets` (model indices, subset of drivable) at rate_hz."""
    pos = np.searchsorted(session.drivable, targets)
    if not np.array_equal(session.drivable[pos], targets):
        raise ValueError("targets must be a subset of the session's drivable neurons")
    rates = np.zeros((1, session.drivable.size))
    rates[0, pos] = rate_hz
    return poisson_draws(rates, n_ticks, rng)
