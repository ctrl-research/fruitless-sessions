from pathlib import Path

from fruitless.conductor.mapper import PULSE_CV, SaxMapper
from fruitless.conductor.tune import load_tune

TUNE = Path(__file__).resolve().parents[1] / "tunes" / "blues-in-f" / "tune.yaml"


def _ro(song_on=1.0, intensity=40.0, pulse=0.3):
    return {"song_on": song_on, "intensity": intensity, "pulse": pulse, "pip10_hz": 80.0}


def test_head_note_sounds_only_when_song_on():
    t = load_tune(TUNE)
    m = SaxMapper(t)
    m.on_step(0, _ro(song_on=1.0))          # F4 starts, fly singing
    m.on_step(1, _ro())
    m.on_step(2, _ro(song_on=0.0))          # A4 starts, fly silent -> no note
    m.on_step(3, _ro(song_on=0.0))
    notes = m.finish(t.duration_s)
    assert [n.midi for n in notes] == [65]
    assert notes[0].source == "melody" and 40 <= notes[0].vel <= 120


def test_pulse_makes_short_notes_and_pushes_early():
    t = load_tune(TUNE)
    m = SaxMapper(t)
    m.on_step(0, _ro(pulse=PULSE_CV * 2))
    notes = m.finish(t.duration_s)
    assert len(notes) == 1
    assert notes[0].dur < t.step_seconds
    assert notes[0].t < 0.0 + 1e-9 or notes[0].t == 0.0   # cannot go before zero


def test_velocity_follows_intensity():
    t = load_tune(TUNE)
    m = SaxMapper(t)
    m.on_step(0, _ro(intensity=10.0))
    m.on_step(2, _ro(intensity=80.0))
    notes = m.finish(t.duration_s)
    assert notes[0].vel < notes[1].vel


def test_solo_starts_a_note_every_beat_on_chord_tones():
    t = load_tune(TUNE)
    m = SaxMapper(t)
    solo0 = 12 * t.steps_per_bar
    for k in range(t.steps_per_bar):        # one bar of F7
        m.on_step(solo0 + k, _ro(intensity=30.0 + k))
    notes = m.finish(t.duration_s)
    assert len(notes) == 4                   # one per beat
    assert all(n.source == "solo" for n in notes)
    assert all(n.midi % 12 in {0, 3, 5, 9, 7, 2, 10} for n in notes)  # F mixolydian
