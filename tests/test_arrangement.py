"""Arrangement mode: written parts gated by the flies. The real MIDI is not in the repo, so the
loader test skips without it and the mapper tests build a tiny Tune by hand."""

from pathlib import Path

import pytest

from fruitless.conductor.mappers import KICK, SNARE, BassMapper, DrumsMapper, PianoMapper
from fruitless.conductor.tune import Section, Tune, load_tune

TAKE_FIVE = Path(__file__).resolve().parents[1] / "tunes" / "take-five"


def _tune() -> Tune:
    # 4/4 at 120, swing eighths (8 steps a bar), one bar, everyone follows a written part
    return Tune(
        name="t", tempo_bpm=120.0, grid="swing8", key="C", chart=[["C7", "", "", ""]],
        form=[Section("head", ("sax",), 1)], roles=["sax", "bass", "drums", "piano"], coupling={},
        free_style=False, melody=[(0.0, 1.0, 72)], arrangement="x.mid",
        parts={
            "bass": [(0.0, 1.0, 36, 90), (2.0, 1.0, 43, 80)],           # beats 1 and 3
            "drums": [(0.0, 0.1, KICK, 100), (1.0, 0.1, SNARE, 95)],   # kick on 1, snare on 2
            "piano": [(1.0, 1.0, 60, 70), (1.0, 1.0, 64, 70), (1.0, 1.0, 67, 70), (1.0, 1.0, 71, 70)],
        },
    )


def test_bass_follows_the_written_line_when_legs_are_loaded():
    t = _tune()
    m = BassMapper(t)
    for step in range(t.steps_per_bar):
        m.on_step(step, {"load": 20.0 if step < 4 else 0.0, "step_l": 0, "step_r": 0})
    notes = m.finish(t.duration_s)
    assert [n.midi for n in notes] == [36]          # beat 3's note is gated out: legs unloaded
    assert notes[0].source == "written"


def test_drums_written_hits_are_gated_by_muscle_groups():
    t = _tune()
    m = DrumsMapper(t)
    m.on_step(0, {"power": 30.0, "steer": 0.0, "hg": 0.0, "burst": 0.0, "gf": 0.0})   # kick passes
    m.on_step(2, {"power": 30.0, "steer": 0.0, "hg": 0.0, "burst": 0.0, "gf": 0.0})   # snare needs steer
    assert [n.midi for n in m.finish(1)] == [KICK]


def test_piano_written_chord_thins_when_the_bump_is_diffuse():
    t = _tune()
    full = PianoMapper(t); full.on_step(2, {"epg_hz": 20.0, "bump_mag": 0.9, "mb_gain": 1.0})
    shell = PianoMapper(t); shell.on_step(2, {"epg_hz": 20.0, "bump_mag": 0.2, "mb_gain": 1.0})
    quiet = PianoMapper(t); quiet.on_step(2, {"epg_hz": 0.0, "bump_mag": 0.9, "mb_gain": 1.0})
    assert len(full.finish(1)) == 4
    assert sorted(n.midi for n in shell.finish(1)) == [60, 71]
    assert quiet.finish(1) == []


@pytest.mark.skipif(not (TAKE_FIVE / "tune.mid").is_file(), reason="tune.mid is not in the repo")
def test_take_five_arrangement_loads():
    t = load_tune(TAKE_FIVE / "tune.yaml")
    assert t.beats_per_bar == 5 and t.total_bars > 100
    assert set(t.parts) == {"sax", "bass", "piano", "drums"}
    assert [s.kind for s in t.form][:3] == ["vamp", "head", "vamp"]
    assert t.chord_at(5 * t.steps_per_bar) == "Ebm7"          # the vamp
    assert t.chord_at(100 * t.steps_per_bar) == "Em7"         # the head out is up a half step
