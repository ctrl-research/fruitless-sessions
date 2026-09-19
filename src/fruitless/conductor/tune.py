"""Tune files: tempo, grid, chart, melody, form, roles, coupling.

See docs/plan.md section 8 for the YAML shape. A loaded Tune knows, for any
grid step, the bar and beat, the chord, the chord-tone and scale pitch classes,
the melody note the soloist should be playing (if in a head section), and
which section of the form we are in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from music21 import converter, harmony
from music21 import key as m21key

GRIDS = {"16th": 4, "8th": 2, "swing8": 2, "quarter": 1}   # steps per beat (4/4)


@dataclass(frozen=True)
class Section:
    kind: str                 # head | solo | trade | free
    who: tuple[str, ...]      # roles soloing (trade alternates through them)
    bars: int                 # length in bars; a chorus for head/solo
    trade_bars: int = 0


@dataclass
class Tune:
    name: str
    tempo_bpm: float
    grid: str
    key: str
    chart: list[list[str]]                    # bars x beats, chord symbols ("" = hold)
    form: list[Section]
    roles: list[str]
    coupling: dict[str, dict[str, float]]
    free_style: bool
    melody: list[tuple[float, float, int]] = field(default_factory=list)  # (start_beat, dur_beats, midi)
    source_dir: Path | None = None

    # ------------------------------------------------------------ timing
    @property
    def steps_per_beat(self) -> int:
        return GRIDS[self.grid]

    @property
    def beats_per_bar(self) -> int:
        return 4

    @property
    def steps_per_bar(self) -> int:
        return self.steps_per_beat * self.beats_per_bar

    @property
    def step_seconds(self) -> float:
        return 60.0 / self.tempo_bpm / self.steps_per_beat

    @property
    def chorus_bars(self) -> int:
        return len(self.chart)

    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.form)

    @property
    def total_steps(self) -> int:
        return self.total_bars * self.steps_per_bar

    @property
    def duration_s(self) -> float:
        return self.total_steps * self.step_seconds

    def swing_offset_s(self, step: int) -> float:
        """For swing8, delay every off-beat eighth to a 2:1 triplet feel."""
        if self.grid != "swing8" or step % 2 == 0:
            return 0.0
        beat = 60.0 / self.tempo_bpm
        return beat * (2.0 / 3.0) - beat * 0.5

    # ------------------------------------------------------------ position
    def section_at(self, step: int) -> tuple[Section, int]:
        """(section, bar offset within it)."""
        bar = step // self.steps_per_bar
        for s in self.form:
            if bar < s.bars:
                return s, bar
            bar -= s.bars
        return self.form[-1], self.form[-1].bars - 1

    def soloist_at(self, step: int) -> str | None:
        sec, bar = self.section_at(step)
        if sec.kind == "head":
            return self.roles[0] if "sax" not in self.roles else "sax"
        if sec.kind == "solo":
            return sec.who[0]
        if sec.kind == "trade" and sec.who:
            return sec.who[(bar // max(1, sec.trade_bars)) % len(sec.who)]
        return None

    def chord_at(self, step: int) -> str | None:
        if not self.chart:
            return None
        bar = (step // self.steps_per_bar) % self.chorus_bars
        beat = (step % self.steps_per_bar) // self.steps_per_beat
        row = self.chart[bar]
        sym = ""
        for b in range(min(beat, len(row) - 1), -1, -1):
            if row[b]:
                sym = row[b]
                break
        if not sym:
            # hold from the previous bar's last chord
            for pb in range(bar - 1, -1, -1):
                prev = [c for c in self.chart[pb] if c]
                if prev:
                    return prev[-1]
        return sym or None

    def melody_at(self, step: int) -> int | None:
        """MIDI pitch the head has at this step, or None for a rest. Only in head sections."""
        sec, bar_in_sec = self.section_at(step)
        if sec.kind != "head" or not self.melody:
            return None
        beat_in_chorus = ((bar_in_sec % self.chorus_bars) * self.beats_per_bar
                          + (step % self.steps_per_bar) / self.steps_per_beat)
        for start, dur, midi in self.melody:
            if start <= beat_in_chorus < start + dur:
                return midi
        return None


# ---------------------------------------------------------------- theory
_chord_cache: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {}


def chord_pitch_classes(symbol: str, key_name: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(chord tones, scale) as pitch classes 0..11 for a chord symbol like 'Bm7b5'.

    The scale is a pragmatic choice per chord quality: dominant -> mixolydian,
    minor 7 -> dorian, half-diminished -> locrian, major -> ionian (or lydian
    when the chord is not the key's tonic). Good enough to comp and solo on.
    """
    k = (symbol, key_name)
    if k in _chord_cache:
        return _chord_cache[k]
    sym = symbol.replace("maj7", "M7").replace("m7b5", "m7b5").replace("Δ", "M7")
    cs = harmony.ChordSymbol(sym)
    root = cs.root().pitchClass
    tones = tuple(sorted({p.pitchClass for p in cs.pitches}))
    quality = cs.chordKind or ""
    if "dominant" in quality:
        mode = (0, 2, 4, 5, 7, 9, 10)
    elif "half-diminished" in quality:
        mode = (0, 1, 3, 5, 6, 8, 10)
    elif "diminished" in quality:
        mode = (0, 2, 3, 5, 6, 8, 9, 11)
    elif quality.startswith("minor"):
        mode = (0, 2, 3, 5, 7, 9, 10)
    else:
        tonic = m21key.Key(key_name).tonic.pitchClass
        mode = (0, 2, 4, 5, 7, 9, 11) if root == tonic else (0, 2, 4, 6, 7, 9, 11)
    scale = tuple(sorted((root + d) % 12 for d in mode))
    _chord_cache[k] = (tones, scale)
    return tones, scale


# ---------------------------------------------------------------- loading
def _parse_form(items: list, roles: list[str]) -> list[Section]:
    out = []
    for it in items:
        if isinstance(it, str):
            if it == "head":
                out.append(Section("head", (), 0))
            elif it.startswith("solo:"):
                out.append(Section("solo", (it.split(":", 1)[1],), 0))
            elif it == "free":
                out.append(Section("free", tuple(roles), 0))
            else:
                raise ValueError(f"unknown form item {it!r}")
        elif isinstance(it, dict):
            (kind, val), = it.items()
            if kind.startswith("trade"):
                n = int(re.sub(r"\D", "", kind) or 4)
                out.append(Section("trade", tuple(val), 0, trade_bars=n))
            elif kind == "solo":
                who, bars = (val, 0) if isinstance(val, str) else (val["who"], int(val.get("choruses", 1)))
                out.append(Section("solo", (who,), bars))
            else:
                raise ValueError(f"unknown form item {it!r}")
    return out


def _load_melody(path: Path) -> list[tuple[float, float, int]]:
    score = converter.parse(str(path))
    notes = []
    for n in score.flatten().notes:
        if n.isRest:
            continue
        p = n.pitches[0] if hasattr(n, "pitches") else n.pitch
        notes.append((float(n.offset), float(n.quarterLength), int(p.midi)))
    return notes


def load_tune(path: Path) -> Tune:
    path = Path(path)
    doc = yaml.safe_load(path.read_text())
    roles = list(doc.get("roles", []))
    chart_raw = doc.get("chart") or []
    chart = [[str(c) if c else "" for c in bar] for bar in chart_raw]
    form = _parse_form(doc.get("form", ["head"]), roles)
    chorus = max(1, len(chart))
    # fill section lengths: head and solo default to one chorus, trade sections to one chorus
    filled = []
    for s in form:
        bars = s.bars or chorus
        if s.kind == "solo" and s.bars:
            bars = s.bars * chorus
        filled.append(Section(s.kind, s.who, bars, s.trade_bars))
    melody = _load_melody(path.parent / doc["melody"]) if doc.get("melody") else []
    return Tune(
        name=doc["name"], tempo_bpm=float(doc.get("tempo_bpm", 120)), grid=doc.get("grid", "swing8"),
        key=doc.get("key", "C"), chart=chart, form=filled, roles=roles,
        coupling=doc.get("coupling", {}), free_style=bool(doc.get("free_style", False)),
        melody=melody, source_dir=path.parent,
    )
