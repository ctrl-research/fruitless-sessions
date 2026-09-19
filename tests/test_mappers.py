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


def _piano(bump_deg=90.0, bump_mag=0.8, epg_hz=20.0, mb_gain=1.0):
    return {"bump_deg": bump_deg, "bump_mag": bump_mag, "epg_hz": epg_hz, "mbon_hz": 5.0, "mb_gain": mb_gain, "pam_hz": 0.0}


def test_piano_comps_on_two_and_four_with_chord_tones():
    from fruitless.conductor.mappers import PianoMapper
    t = load_tune(TUNE)
    m = PianoMapper(t)
    for step in range(t.steps_per_bar):        # one bar of F7
        m.on_step(step, _piano())
    notes = m.finish(t.duration_s)
    steps = sorted({n.step for n in notes})
    assert steps == [2, 6, 7]                  # beats 2 and 4, and the "and" of 4
    assert all(n.midi % 12 in {9, 0, 3, 7} for n in notes)   # A C Eb G: 3rd 5th 7th 9th of F7


def test_piano_shell_voicing_when_bump_is_diffuse_and_silent_when_ring_is_quiet():
    from fruitless.conductor.mappers import PianoMapper
    t = load_tune(TUNE)
    m = PianoMapper(t)
    m.on_step(2, _piano(bump_mag=0.2))         # diffuse: two-note shell
    m.on_step(6, _piano(epg_hz=0.0))           # ring silent: nothing
    notes = m.finish(t.duration_s)
    assert len(notes) == 2 and all(n.step == 2 for n in notes)


def test_piano_velocity_scales_with_mushroom_body_gain():
    from fruitless.conductor.mappers import PianoMapper
    t = load_tune(TUNE)
    lo = PianoMapper(t); lo.on_step(2, _piano(mb_gain=0.6))
    hi = PianoMapper(t); hi.on_step(2, _piano(mb_gain=1.4))
    assert lo.finish(1)[0].vel < hi.finish(1)[0].vel


def test_key_from_bump_walks_the_circle_of_fifths():
    from fruitless.conductor.mappers import key_from_bump
    from fruitless.flies.piano import Piano
    assert key_from_bump(0.0) == 0            # C at the start of the ring
    assert key_from_bump(46.0) == 2           # wedge 2: D
    assert key_from_bump(350.0) == 5          # last wedge: F
    for pc in range(12):                      # every key reads back from the wedge it is written to
        w = Piano.wedge_for_pitch_class(pc)
        deg = (w - 0.5) / 8 * 360
        assert Piano.wedge_for_pitch_class(key_from_bump(deg)) == w
