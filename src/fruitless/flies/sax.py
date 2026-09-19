"""The soloist: courtship song circuit driving wing motor neurons.

Verified in the model on 2026-09-19 (docs/log.md): Poisson drive on the male
specific `pC1_*` cluster fires `pIP10`, then `dPR1` and `TN1*` in the nerve
cord, then the wing motor neurons, scaling with drive. `vPR6` stays silent and
is shown but not read.

Readout per grid step:
  song_on     1 when TN1 rate exceeds a threshold, else 0
  intensity   wing MN population rate in Hz
  pulse       burstiness of the wing MN spikes (CV over 10 ms bins); high = pulse song
  pip10_hz    pIP10 rate, the command signal, for the page
"""

from __future__ import annotations

import numpy as np

from fruitless.flies.base import Fly, Readout
from fruitless.flies.select import Selection

WING_MN_TYPES = (
    r"DLMn.*", r"DVMn.*", r"b[123] MN", r"hg[1-4] MN", r"i[12] MN", r"iii[13] MN",
    r"ps[12] MN", r"tp[12] MN", r"tpn MN",
)

CIRCUIT = {
    "pC1": Selection("pC1", types=(r"pC1_.*",)),
    "pC1x": Selection("pC1x", types=(r"pC1x_.*",)),
    "pIP10": Selection("pIP10", types=(r"pIP10",)),
    "vPR6": Selection("vPR6", types=(r"vPR6",)),
    "dPR1": Selection("dPR1", types=(r"dPR1",)),
    "TN1": Selection("TN1", types=(r"TN1.*",)),
    "wing_mn": Selection("wing_mn", types=WING_MN_TYPES),
}

DRIVE = {"pC1": CIRCUIT["pC1"]}

SONG_ON_TN1_HZ = 5.0


class Sax(Fly):
    def __init__(self):
        super().__init__(role="sax", circuit=CIRCUIT, drive=DRIVE,
                         readout_names=("song_on", "intensity", "pulse", "pip10_hz"),
                         # the command and motor side of the song pathway plus escape;
                         # pC1 (148) and the ears (~340) stay as soma points
                         mesh_groups=("pIP10", "vPR6", "dPR1", "TN1", "wing_mn", "giant_fiber", "gfc"))

    def readout(self, counts: np.ndarray, events: np.ndarray, t0: int, n_ticks: int) -> Readout:
        tn1 = self.rate_hz(counts, self.indices("TN1"), n_ticks)
        wing = self.rate_hz(counts, self.indices("wing_mn"), n_ticks)
        pulse = self.burstiness(events, self.indices("wing_mn"), t0, n_ticks)
        pip10 = self.rate_hz(counts, self.indices("pIP10"), n_ticks)
        return Readout(self.readout_names,
                       np.array([1.0 if tn1 > SONG_ON_TN1_HZ else 0.0, wing, pulse, pip10], np.float32))
