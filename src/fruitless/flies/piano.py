"""The pianist: the central complex heading ring as a circle of fifths.

Probe on 2026-09-19 (docs/log.md, "does the ring hold a bump?"): the ring
attractor's wiring is present but the LIF has no persistent activity, so a
bump lasts only while driven. The conductor writes the current key into the
ring by driving the EPG wedge for the chord root (as a landmark would set
heading); in free style only the ear imbalance pushes PEN_a left and right and
the key wanders. The fly's readout is the EPG population vector.

Readout per grid step:
  bump_deg   population-vector angle of EPG activity, degrees 0..360
  bump_mag   population-vector magnitude 0..1 (1 = one wedge, 0 = uniform or silent)
  epg_hz     EPG population rate
  mbon_hz    MBON population rate (mushroom body output)
  mb_gain    mbon_hz relative to its running baseline, clipped 0.5..1.5; scales note velocity
  pam_hz     PAM dopaminergic rate (reward drive echoed back for the page)
"""

from __future__ import annotations

import re

import numpy as np

from fruitless.flies.base import Fly, Readout
from fruitless.flies.select import MUSHROOM_BODY, Selection

WEDGES = 8

CIRCUIT = {
    "EPG": Selection("EPG", types=(r"EPG",)),
    "PEN_a": Selection("PEN_a", types=(r"PEN_a\(PEN1\)",)),
    "PEN_b": Selection("PEN_b", types=(r"PEN_b\(PEN2\)",)),
    "Delta7": Selection("Delta7", types=(r"Delta7",)),
    "ER": Selection("ER", types=(r"ER[1-6].*",)),
    **MUSHROOM_BODY,
    "PAM": Selection("PAM", types=(r"PAM\d+.*",)),
    "PPL1": Selection("PPL1", types=(r"PPL1\d+.*",)),
}


def wedge_of(instance: str | None) -> int | None:
    m = re.search(r"_([LR])(\d)", instance or "")
    return int(m.group(2)) if m else None


def wedge_angle(k: int) -> float:
    return 2 * np.pi * ((k - 0.5) / WEDGES)


class Piano(Fly):
    def __init__(self):
        super().__init__(role="piano", circuit=CIRCUIT, drive={},
                         readout_names=("bump_deg", "bump_mag", "epg_hz", "mbon_hz", "mb_gain", "pam_hz"),
                         mesh_groups=("EPG", "PEN_a", "PEN_b", "Delta7", "mbon", "PPL1", "giant_fiber", "gfc"))
        self._epg_angles: np.ndarray | None = None
        self._mbon_base = 5.0

    def derive(self, r, pack) -> None:
        epg = self.indices("EPG")
        inst = r.instances_of(epg)
        wedges = np.array([wedge_of(n) or 0 for n in inst])
        self._epg_angles = np.array([wedge_angle(k) for k in wedges])
        for k in range(1, WEDGES + 1):
            self.add_group(f"epg_w{k}", epg[wedges == k], drive=True)
        pen = self.indices("PEN_a")
        pinst = r.instances_of(pen)
        self.add_group("pen_a_L", pen[[("_L" in (n or "")) for n in pinst]], drive=True)
        self.add_group("pen_a_R", pen[[("_R" in (n or "")) for n in pinst]], drive=True)
        self.add_group("PAM", self.indices("PAM"), drive=True)
        self.add_group("PPL1", self.indices("PPL1"), drive=True)

    @staticmethod
    def wedge_for_pitch_class(pc: int) -> int:
        """Circle of fifths onto the eight wedges: C at wedge 1, moving by fifths."""
        fifths = (pc * 7) % 12                  # position of pc on the circle of fifths
        return int(np.floor(fifths / 12 * WEDGES)) + 1

    def readout(self, counts: np.ndarray, events: np.ndarray, t0: int, n_ticks: int) -> Readout:
        epg = self.indices("EPG")
        c = counts[epg].astype(float)
        if c.sum() > 0 and self._epg_angles is not None:
            z = (c * np.exp(1j * self._epg_angles)).sum() / c.sum()
            deg, mag = float(np.degrees(np.angle(z)) % 360), float(abs(z))
        else:
            deg, mag = 0.0, 0.0
        epg_hz = self.rate_hz(counts, epg, n_ticks)
        mbon_hz = self.rate_hz(counts, self.indices("mbon"), n_ticks)
        self._mbon_base += (mbon_hz - self._mbon_base) * 0.05
        gain = float(np.clip(mbon_hz / max(1.0, self._mbon_base), 0.5, 1.5))
        pam_hz = self.rate_hz(counts, self.indices("PAM"), n_ticks)
        return Readout(self.readout_names, np.array([deg, mag, epg_hz, mbon_hz, gain, pam_hz], np.float32))
