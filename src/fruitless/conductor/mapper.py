"""Readouts to notes. The only place where spikes become music.

Every rule here is deliberately small and stated in the docstring, because the
page shows it. The fly never chooses a pitch in a head section: the melody does.
The fly decides whether the note sounds, how loud, how short, and whether it
lands early or late inside the grid step.

Sax rules
  sounds     song_on == 1 in the step where the melody note starts
  velocity   intensity (wing MN Hz) mapped 0..80 -> 40..120, clipped
  duration   pulse > PULSE_CV: a short accented note (0.55 step); else legato until
             the melody's next note or the end of the step where song_on drops
  timing     grid time plus swing offset, then pushed early by up to 30 ms when
             pulse is high and late by up to 40 ms when intensity is low
  solo       pitch = chord scale degree picked by intensity relative to the
             running mean (louder = higher), restricted to chord tones on beats
             1 and 3; a new note on every beat, and on every off-beat step too
             when pulse is high; rests happen only when song_on drops
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fruitless.conductor.tune import Tune, chord_pitch_classes

PULSE_CV = 0.9
SOLO_LOW, SOLO_HIGH = 55, 79    # G3 .. G5 for the soloist's range


@dataclass
class Note:
    t: float           # seconds
    dur: float
    midi: int
    vel: int
    step: int
    role: str
    source: str        # melody | solo


@dataclass
class SaxMapper:
    tune: Tune
    role: str = "sax"
    notes: list[Note] = field(default_factory=list)
    _open: Note | None = None
    _last_melody: int | None = None
    _intensity_mean: float = 30.0
    _last_chord: str | None = None

    def step_time(self, step: int, readout: dict[str, float]) -> float:
        t = step * self.tune.step_seconds + self.tune.swing_offset_s(step)
        pulse = readout.get("pulse", 0.0)
        intensity = readout.get("intensity", 0.0)
        early = -0.03 * min(1.0, max(0.0, (pulse - PULSE_CV) / PULSE_CV))
        late = 0.04 * min(1.0, max(0.0, (20.0 - intensity) / 20.0))
        return max(0.0, t + early + late)

    @staticmethod
    def velocity(intensity: float) -> int:
        return int(np.clip(40 + intensity / 80.0 * 80.0, 40, 120))

    def _close(self, t_end: float) -> None:
        if self._open is not None:
            self._open.dur = max(0.05, t_end - self._open.t)
            self.notes.append(self._open)
            self._open = None

    def on_step(self, step: int, readout: dict[str, float]) -> None:
        tune = self.tune
        sec, _ = tune.section_at(step)
        song_on = readout.get("song_on", 0.0) >= 0.5
        intensity = readout.get("intensity", 0.0)
        pulse = readout.get("pulse", 0.0)
        t = self.step_time(step, readout)
        step_s = tune.step_seconds
        self._intensity_mean += (intensity - self._intensity_mean) * 0.1

        if sec.kind == "head" and tune.soloist_at(step) == self.role:
            m = tune.melody_at(step)
            starts = m is not None and m != self._last_melody
            # a repeated pitch with a note boundary also starts (melody_at cannot see that);
            # approximate: treat every beat boundary with the same pitch as a re-attack
            if m is not None and m == self._last_melody and step % tune.steps_per_beat == 0:
                starts = True
            self._last_melody = m
            if m is None:
                self._close(t)
            elif starts:
                self._close(t)
                if song_on:
                    dur = 0.55 * step_s if pulse > PULSE_CV else step_s
                    self._open = Note(t, dur, m, self.velocity(intensity), step, self.role, "melody")
                    if pulse > PULSE_CV:
                        self._close(t + dur)
            elif self._open is not None and not song_on:
                self._close(t)
            return

        if sec.kind == "solo" and tune.soloist_at(step) == self.role:
            chord = tune.chord_at(step)
            if not song_on or chord is None:
                self._close(t)
                self._last_chord = chord
                return
            tones, scale = chord_pitch_classes(chord, tune.key)
            on_beat = step % (2 * tune.steps_per_beat) == 0
            pool = tones if on_beat else scale
            pitches = [p for p in range(SOLO_LOW, SOLO_HIGH + 1) if p % 12 in pool]
            rel = (intensity - self._intensity_mean) / max(10.0, self._intensity_mean)
            k = int(np.clip(round((0.5 + 0.5 * np.tanh(rel)) * (len(pitches) - 1)), 0, len(pitches) - 1))
            midi = pitches[k]
            on_any_beat = step % tune.steps_per_beat == 0
            new = on_any_beat or pulse > PULSE_CV or chord != self._last_chord or self._open is None
            self._last_chord = chord
            if new:
                self._close(t)
                dur = 0.55 * step_s if pulse > PULSE_CV else step_s
                self._open = Note(t, dur, midi, self.velocity(intensity), step, self.role, "solo")
                if pulse > PULSE_CV:
                    self._close(t + dur)
            return

        # not this fly's section
        self._close(t)

    def finish(self, t_end: float) -> list[Note]:
        self._close(t_end)
        return sorted(self.notes, key=lambda n: n.t)
