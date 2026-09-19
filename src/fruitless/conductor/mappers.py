"""Readouts to notes for the rhythm section. Rules stated here, shown on the page.

Bass rules
  a footfall is a note: on each grid step, if a tripod's step flag is up and it
  was down on the previous step, one note starts. Left tripod plays the root or
  fifth of the current chord (alternating), right tripod plays the third or
  seventh, approach tones on the last eighth before a chord change.
  velocity   from the stepping tripod's mean leg MN rate, 0..60 Hz -> 50..115
  duration   until the next footfall, at most one beat (walking bass)
  register   E1..G3

Piano rules
  comps on beats 2 and 4 and on the "and" of 4 (anticipation), rootless
  voicings of the current chord: third, fifth, seventh plus the ninth when the
  bump is sharp (bump_mag > 0.6), a two-note shell when it is diffuse.
  velocity   from EPG population rate, 0..40 Hz -> 45..100, times mb_gain
  register   voicing centred near the bump angle mapped onto C3..C5
  free style the chord is whatever key the bump points at, as a dominant 7th

Drums rules (GM drum map)
  kick 36    when power MN rate rises above its running mean on a beat
  ride 51    every beat while power rate > 20 Hz, velocity from rate
  hi-hat 42  every off-beat step while steer rate > 15 Hz
  snare 38   on beats 2 and 4 when steer rate > 25 Hz; ghost notes when burst > 0.9
  toms 45/47 when hg rate > 20 Hz on an off-beat
  crash 49   when the giant fiber rate > 5 Hz (startle)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fruitless.conductor.mapper import Note
from fruitless.conductor.tune import Tune, chord_pitch_classes

BASS_LOW, BASS_HIGH = 28, 55


def _nearest(pc: int, lo: int, hi: int, prefer: int | None) -> int:
    cands = [p for p in range(lo, hi + 1) if p % 12 == pc]
    if prefer is None:
        return cands[len(cands) // 2]
    return min(cands, key=lambda p: abs(p - prefer))


@dataclass
class BassMapper:
    tune: Tune
    role: str = "bass"
    notes: list[Note] = field(default_factory=list)
    _open: Note | None = None
    _prev_l: float = 0.0
    _prev_r: float = 0.0
    _alt: int = 0
    _last_pitch: int | None = None

    def _close(self, t_end: float) -> None:
        if self._open is not None:
            self._open.dur = max(0.05, t_end - self._open.t)
            self.notes.append(self._open)
            self._open = None

    def on_step(self, step: int, readout: dict[str, float]) -> None:
        tune = self.tune
        t = step * tune.step_seconds + tune.swing_offset_s(step)
        chord = tune.chord_at(step)
        l, r = readout.get("step_l", 0.0), readout.get("step_r", 0.0)
        onset_l = l >= 0.5 and self._prev_l < 0.5
        onset_r = r >= 0.5 and self._prev_r < 0.5
        self._prev_l, self._prev_r = l, r
        if chord is None or not (onset_l or onset_r):
            if self._open is not None and t - self._open.t >= 60.0 / tune.tempo_bpm:
                self._close(t)
            return
        tones, _scale = chord_pitch_classes(chord, tune.key)
        root = tones[0]
        fifth = tones[2] if len(tones) > 2 else (root + 7) % 12
        third = tones[1] if len(tones) > 1 else (root + 4) % 12
        seventh = tones[3] if len(tones) > 3 else (root + 10) % 12
        next_chord = tune.chord_at(step + 1)
        if next_chord and next_chord != chord and (step + 1) % tune.steps_per_bar == 0:
            # approach: a half step below the next root
            nroot = chord_pitch_classes(next_chord, tune.key)[0][0]
            pc = (nroot - 1) % 12
        elif onset_l:
            pc = root if self._alt % 2 == 0 else fifth
            self._alt += 1
        else:
            pc = third if self._alt % 2 == 0 else seventh
        rate = np.mean([readout.get(k, 0.0) for k in (("fl_L", "ml_R", "hl_L") if onset_l else ("fl_R", "ml_L", "hl_R"))])
        vel = int(np.clip(50 + rate / 60.0 * 65.0, 50, 115))
        midi = _nearest(pc, BASS_LOW, BASS_HIGH, self._last_pitch)
        self._last_pitch = midi
        self._close(t)
        self._open = Note(t, 60.0 / tune.tempo_bpm, midi, vel, step, self.role, "walk")

    def finish(self, t_end: float) -> list[Note]:
        self._close(t_end)
        return sorted(self.notes, key=lambda n: n.t)


KICK, SNARE, HAT, RIDE, TOM_LO, TOM_HI, CRASH = 36, 38, 42, 51, 45, 47, 49


@dataclass
class DrumsMapper:
    tune: Tune
    role: str = "drums"
    notes: list[Note] = field(default_factory=list)
    _power_mean: float = 20.0
    _crash_until: float = -1.0

    def _hit(self, t: float, midi: int, vel: int, step: int, source: str) -> None:
        self.notes.append(Note(t, 0.12, midi, int(np.clip(vel, 1, 127)), step, self.role, source))

    def on_step(self, step: int, readout: dict[str, float]) -> None:
        tune = self.tune
        t = step * tune.step_seconds + tune.swing_offset_s(step)
        spb = tune.steps_per_beat
        beat = (step % tune.steps_per_bar) // spb
        on_beat = step % spb == 0
        bpb = tune.beats_per_bar
        # accents: 4/4 kicks 1 and 3 with snare on 2 and 4; 5/4 groups 3 + 2, kick on 1 and 4,
        # snare on 3 and 5 (the Take Five feel)
        kick_beats = (0, 3) if bpb == 5 else (0, 2) if bpb == 4 else (0,)
        snare_beats = (2, 4) if bpb == 5 else (1, 3) if bpb == 4 else tuple(range(1, bpb, 2))
        power, steer, hg = readout.get("power", 0.0), readout.get("steer", 0.0), readout.get("hg", 0.0)
        burst, gf = readout.get("burst", 0.0), readout.get("gf", 0.0)
        rising = power > self._power_mean * 1.05
        self._power_mean += (power - self._power_mean) * 0.15
        if on_beat and power > 20:
            self._hit(t, RIDE, 60 + power, step, "ride")
            if rising or beat in kick_beats:
                self._hit(t, KICK, 70 + power, step, "kick")
        if not on_beat and steer > 15:
            self._hit(t, HAT, 40 + steer, step, "hat")
        if on_beat and beat in snare_beats and steer > 25:
            self._hit(t, SNARE, 60 + steer, step, "snare")
        elif burst > 0.9 and steer > 15:
            self._hit(t, SNARE, 35 + 20 * burst, step, "ghost")
        if not on_beat and hg > 20:
            self._hit(t, TOM_LO if step % 4 else TOM_HI, 55 + hg, step, "tom")
        if gf > 5 and t > self._crash_until:
            self._hit(t, CRASH, 110, step, "crash")
            self._crash_until = t + 1.0

    def finish(self, _t_end: float) -> list[Note]:
        return sorted(self.notes, key=lambda n: n.t)


PIANO_LOW, PIANO_HIGH = 48, 72
KEY_ORDER = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]   # circle of fifths from C


def key_from_bump(deg: float) -> int:
    """Pitch class at a ring angle: eight wedges around the circle of fifths.

    Inverse of Piano.wedge_for_pitch_class, which puts fifths position f at wedge
    floor(f * 8 / 12): wedge k0 reads back as fifths position floor(1.5 k0 + 0.75),
    so wedges 0..7 name C D A B F# Ab Eb F."""
    k0 = int(np.floor((deg % 360) / 360.0 * 8))           # wedge 0..7
    return KEY_ORDER[int(np.floor(1.5 * k0 + 0.75)) % 12]


@dataclass
class PianoMapper:
    tune: Tune
    role: str = "piano"
    notes: list[Note] = field(default_factory=list)

    def on_step(self, step: int, readout: dict[str, float]) -> None:
        tune = self.tune
        spb = tune.steps_per_beat
        beat = (step % tune.steps_per_bar) // spb
        on_beat = step % spb == 0
        bpb = tune.beats_per_bar
        comp_beats = (1, 3) if bpb == 4 else (1, 3) if bpb == 5 else tuple(range(1, bpb, 2))
        and_of_four = beat == bpb - 1 and step % spb == spb // 2 and spb > 1
        if not ((on_beat and beat in comp_beats) or and_of_four):
            return
        chord = tune.chord_at(step)
        if chord is None:
            return
        tones, _ = chord_pitch_classes(chord, tune.key)
        mag = readout.get("bump_mag", 0.0)
        epg = readout.get("epg_hz", 0.0)
        gain = readout.get("mb_gain", 1.0)
        if epg < 1.0:
            return                                          # the ring is silent: no comp
        third, fifth, seventh = (tones[1:2] or tones[:1])[0], (tones[2:3] or tones[:1])[0], (tones[3:4] or tones[:1])[0]
        pcs = [third, seventh] if mag < 0.6 else [third, fifth, seventh, (tones[0] + 2) % 12]
        centre = PIANO_LOW + (readout.get("bump_deg", 180.0) / 360.0) * (PIANO_HIGH - PIANO_LOW)
        t = step * tune.step_seconds + tune.swing_offset_s(step)
        vel = int(np.clip((45 + epg / 40.0 * 55.0) * gain, 30, 115))
        dur = 0.9 * tune.step_seconds * (2 if and_of_four else 1)
        for pc in pcs:
            midi = _nearest(pc, PIANO_LOW, PIANO_HIGH, round(centre))
            self.notes.append(Note(t, dur, midi, vel, step, self.role, "comp"))

    def finish(self, _t_end: float) -> list[Note]:
        return sorted(self.notes, key=lambda n: n.t)
