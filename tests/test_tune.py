from pathlib import Path

from fruitless.conductor.tune import chord_pitch_classes, load_tune

TUNE = Path(__file__).resolve().parents[1] / "tunes" / "blues-in-f" / "tune.yaml"


def test_blues_structure():
    t = load_tune(TUNE)
    assert t.chorus_bars == 12 and t.total_bars == 36
    assert t.steps_per_bar == 8 and t.total_steps == 288
    assert abs(t.duration_s - 72.0) < 1e-9
    kinds = [s.kind for s in t.form]
    assert kinds == ["head", "solo", "head"]
    assert t.soloist_at(0) == "sax" and t.soloist_at(12 * 8) == "sax"


def test_chords_hold_across_empty_beats():
    t = load_tune(TUNE)
    assert t.chord_at(0) == "F7"
    assert t.chord_at(3) == "F7"          # beat 2 of bar 1 holds
    assert t.chord_at(8) == "Bb7"
    assert t.chord_at(8 * 8) == "C7"      # bar 9
    assert t.chord_at(12 * 8) == "F7"     # wraps into the solo chorus


def test_melody_only_in_head():
    t = load_tune(TUNE)
    assert t.melody_at(0) == 65           # F4
    assert t.melody_at(12 * 8) is None    # solo section
    assert t.melody_at(24 * 8) == 65      # head out


def test_swing_offset_only_on_offbeats():
    t = load_tune(TUNE)
    assert t.swing_offset_s(0) == 0.0
    assert abs(t.swing_offset_s(1) - (0.5 * 2 / 3 - 0.25)) < 1e-9


def test_chord_theory():
    tones, scale = chord_pitch_classes("F7", "F")
    assert tones == (5, 9, 0, 3)          # F A C Eb, ordered from the root
    assert 10 in scale and 4 not in scale  # mixolydian: Eb yes, E no
    tones, _ = chord_pitch_classes("Bm7b5", "C")
    assert tones == (11, 2, 5, 9)         # B D F A


def test_flat_roots():
    tones, _ = chord_pitch_classes("Ebm7", "e-")
    assert tones == (3, 6, 10, 1)             # Eb Gb Bb Db from the root
    assert chord_pitch_classes("Bb7", "F")[0] == (10, 2, 5, 8)


def test_take_five_meter():
    from pathlib import Path as _P

    import pytest
    d = _P(__file__).resolve().parents[1] / "tunes" / "take-five"
    if not (d / "tune.mid").is_file():
        pytest.skip("tune.mid is not in the repo")
    t = load_tune(d / "tune.yaml")
    assert t.beats_per_bar == 5 and t.steps_per_bar == 10
    assert t.chord_at(5 * t.steps_per_bar) == "Ebm7"          # bar 6, the vamp
