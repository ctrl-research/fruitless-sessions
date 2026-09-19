from pathlib import Path

from fruitless.conductor.mappers import CRASH, HAT, KICK, RIDE, SNARE, BassMapper, DrumsMapper
from fruitless.conductor.tune import load_tune

TUNE = Path(__file__).resolve().parents[1] / "tunes" / "blues-in-f" / "tune.yaml"


def _bass(step_l=0.0, step_r=0.0, rate=30.0):
    ro = {k: rate for k in ("fl_L", "fl_R", "ml_L", "ml_R", "hl_L", "hl_R")}
    ro |= {"step_l": step_l, "step_r": step_r, "load": rate}
    return ro


def test_bass_footfall_onsets_become_notes_on_chord_tones():
    t = load_tune(TUNE)
    m = BassMapper(t)
    m.on_step(0, _bass(step_l=1.0))      # onset left -> root of F7
    m.on_step(1, _bass(step_l=1.0))      # still up: no new note
    m.on_step(2, _bass(step_r=1.0))      # onset right -> third or seventh
    m.on_step(3, _bass())
    notes = m.finish(t.duration_s)
    assert len(notes) == 2
    assert notes[0].midi % 12 == 5        # F
    assert notes[1].midi % 12 in (9, 3)   # A or Eb
    assert all(28 <= n.midi <= 55 for n in notes)


def test_bass_velocity_tracks_leg_rate():
    t = load_tune(TUNE)
    m = BassMapper(t)
    m.on_step(0, _bass(step_l=1.0, rate=10.0))
    m.on_step(1, _bass())
    m.on_step(2, _bass(step_l=1.0, rate=55.0))
    notes = m.finish(t.duration_s)
    assert notes[0].vel < notes[1].vel


def _drums(power=30.0, steer=30.0, hg=0.0, burst=0.3, gf=0.0):
    return {"power": power, "steer": steer, "hg": hg, "burst": burst, "gf": gf}


def test_drums_pattern_over_one_bar():
    t = load_tune(TUNE)
    m = DrumsMapper(t)
    for step in range(t.steps_per_bar):
        m.on_step(step, _drums())
    notes = m.finish(t.duration_s)
    kinds = [n.midi for n in notes]
    assert kinds.count(RIDE) == 4            # every beat
    assert kinds.count(HAT) == 4             # every off-beat step
    assert kinds.count(SNARE) == 2           # beats 2 and 4
    assert kinds.count(KICK) >= 2            # at least beats 1 and 3


def test_drums_crash_on_giant_fiber_once_per_second():
    t = load_tune(TUNE)
    m = DrumsMapper(t)
    m.on_step(0, _drums(gf=20.0))
    m.on_step(1, _drums(gf=20.0))
    m.on_step(2, _drums(gf=20.0))
    notes = [n for n in m.finish(t.duration_s) if n.midi == CRASH]
    assert len(notes) == 1
