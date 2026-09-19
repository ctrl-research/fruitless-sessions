"""The drummer: wing motor neurons beating the kit.

Wings are the cheap motor output of this connectome: any descending drive
recruits wing MNs at about 40 Hz, and so does sound on the Johnston's organ
(docs/log.md). The drummer is driven by the steering descending neurons
DNa02 and by what it hears. Left and right wing rates were symmetric under
every drive tested, so drum voices split by muscle type, not side.

Readout per grid step:
  power     DLMn + DVMn rate (indirect flight power muscles): kick and ride
  steer     b1..b3, i1, i2, iii1, iii3 rate (direct steering muscles): snare and hi-hat
  hg        hg1..hg4 rate: toms
  burst     coefficient of variation of all wing MN spikes over 10 ms bins: fills
  gf        giant fiber rate: crash
"""

from __future__ import annotations

import numpy as np

from fruitless.flies.base import Fly, Readout
from fruitless.flies.select import Selection

CIRCUIT = {
    "power_mn": Selection("power_mn", types=(r"DLMn.*", r"DVMn.*")),
    "steer_mn": Selection("steer_mn", types=(r"b[123] MN", r"i[12] MN", r"iii[13] MN", r"ps[12] MN", r"tp[12] MN", r"tpn MN")),
    "hg_mn": Selection("hg_mn", types=(r"hg[1-4] MN",)),
    "DNa02": Selection("DNa02", types=(r"DNa02",)),
}
DRIVE = {"DNa02": CIRCUIT["DNa02"]}


class Drums(Fly):
    def __init__(self):
        super().__init__(role="drums", circuit=CIRCUIT, drive=DRIVE,
                         readout_names=("power", "steer", "hg", "burst", "gf"),
                         mesh_groups=("power_mn", "steer_mn", "hg_mn", "DNa02", "giant_fiber", "gfc"))

    def readout(self, counts: np.ndarray, events: np.ndarray, t0: int, n_ticks: int) -> Readout:
        power = self.rate_hz(counts, self.indices("power_mn"), n_ticks)
        steer = self.rate_hz(counts, self.indices("steer_mn"), n_ticks)
        hg = self.rate_hz(counts, self.indices("hg_mn"), n_ticks)
        wing = np.concatenate([self.indices("power_mn"), self.indices("steer_mn"), self.indices("hg_mn")])
        burst = self.burstiness(events, wing, t0, n_ticks)
        gf = self.rate_hz(counts, self.indices("giant_fiber"), n_ticks)
        return Readout(self.readout_names, np.array([power, steer, hg, burst, gf], np.float32))
