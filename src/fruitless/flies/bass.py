"""The bass: six legs walking the line.

Verified in the model on 2026-09-19 (docs/log.md, "what moves the legs?"):
descending walking commands barely move leg motor neurons in this
connectome, but each leg's excitatory premotor pool, the top 60 positively
weighted presynaptic partners of that leg's motor neurons, fires that leg
selectively. The conductor drives the tripod pools in alternation on the
beat. The gait timing is the conductor's; the fly contributes which motor
neurons fire, how hard, and the crosstalk between legs.

Readout per grid step:
  fl_L .. hl_R   leg MN population rate per leg, Hz (six values)
  step_l, step_r one when the left / right tripod's rate exceeds a threshold
  load           mean leg MN rate over all legs
"""

from __future__ import annotations

import numpy as np

from fruitless.flies.base import Fly, Readout
from fruitless.flies.select import Selection

LEG_MN = (r"(Ti|Tr|Fe|Ta|ltm.*|Sternal.*|Sternotrochanter|Tergopleural.*|Pleural.*|Tergotr\.|Acc\. .*) ?.*MN",)
LEGS = ("fl_L", "fl_R", "ml_L", "ml_R", "hl_L", "hl_R")
TRIPOD_A = ("fl_L", "ml_R", "hl_L")
TRIPOD_B = ("fl_R", "ml_L", "hl_R")
STEP_HZ = 15.0

CIRCUIT = {
    f"leg_{leg}": Selection(f"leg_{leg}", types=LEG_MN, superclasses=("vnc_motor",),
                            subclass=(leg.split("_")[0],), side=leg.split("_")[1])
    for leg in LEGS
}
CIRCUIT["walk_dn"] = Selection("walk_dn", types=(r"DNp09", r"DNa01", r"DNa02", r"MDN"))


class Bass(Fly):
    def __init__(self):
        super().__init__(role="bass", circuit=CIRCUIT, drive={},
                         readout_names=(*LEGS, "step_l", "step_r", "load"),
                         mesh_groups=tuple(f"leg_{leg}" for leg in LEGS) + ("giant_fiber", "gfc"))

    def derive(self, r, pack) -> None:
        for leg in LEGS:
            pool = self.excitatory_partners(pack, self.indices(f"leg_{leg}"), n=60,
                                            superclass_of=r.superclass_of)
            self.add_group(f"pool_{leg}", pool, drive=True)
            self.add_group(f"pool_{leg}", pool)   # also shown on the page

    def readout(self, counts: np.ndarray, events: np.ndarray, t0: int, n_ticks: int) -> Readout:
        rates = [self.rate_hz(counts, self.indices(f"leg_{leg}"), n_ticks) for leg in LEGS]
        by = dict(zip(LEGS, rates, strict=True))
        a = float(np.mean([by[k] for k in TRIPOD_A]))
        b = float(np.mean([by[k] for k in TRIPOD_B]))
        return Readout(self.readout_names, np.array([*rates, 1.0 if a > STEP_HZ else 0.0,
                                                     1.0 if b > STEP_HZ else 0.0,
                                                     float(np.mean(rates))], np.float32))
