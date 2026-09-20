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

import numpy as np
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
    free_chord: str | None = None     # set by the conductor in free style (from the piano's bump)
    meter_beats: int = 4              # beats per bar (4 for 4/4, 5 for 5/4); the beat is a quarter
    # arrangement mode: written parts per role, (start_beat, dur_beats, midi, velocity) from bar 1
    parts: dict[str, list[tuple[float, float, int, int]]] = field(default_factory=dict)
    arrangement: str | None = None
    # how faithfully written parts are played: "gated" lets a fly drop a note when its circuit
    # is quiet at that step; "strict" always sounds the written note and the fly only shapes
    # its velocity and articulation
    written: str = "gated"

    # ------------------------------------------------------------ timing
    @property
    def steps_per_beat(self) -> int:
        return GRIDS[self.grid]

    @property
    def beats_per_bar(self) -> int:
        return self.meter_beats

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
        if sec.kind == "free":
            return "sax" if "sax" in self.roles else None    # everyone plays; the sax carries the line
        return None

    def chord_at(self, step: int) -> str | None:
        if not self.chart:
            return self.free_chord
        bar = (step // self.steps_per_bar) % self.chorus_bars
        if self.arrangement:
            bar = min(step // self.steps_per_bar, self.chorus_bars - 1)
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
        if self.arrangement:
            beat = step / self.steps_per_beat        # arranged melodies run from bar 1, no chorus wrap
        else:
            beat = ((bar_in_sec % self.chorus_bars) * self.beats_per_bar
                    + (step % self.steps_per_bar) / self.steps_per_beat)
        for start, dur, midi in self.melody:
            if start <= beat < start + dur:
                return midi
        return None

    def part_onsets(self, role: str, step: int) -> list[tuple[int, int, float]]:
        """Written notes of `role` starting within this grid step: (midi, velocity, dur_beats)."""
        return [(m, v, d) for (_st, m, v, d) in self.part_onsets_timed(role, step)]

    def part_onsets_timed(self, role: str, step: int) -> list[tuple[float, int, int, float]]:
        """Like part_onsets, with each note's exact written start in seconds first."""
        notes = self.parts.get(role)
        if not notes:
            return []
        b0 = step / self.steps_per_beat
        b1 = (step + 1) / self.steps_per_beat
        beat_s = 60.0 / self.tempo_bpm
        return [(st * beat_s, m, v, d) for (st, d, m, v) in notes if b0 <= st < b1]


# ---------------------------------------------------------------- theory
_chord_cache: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {}


def chord_pitch_classes(symbol: str, key_name: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(chord tones, scale) as pitch classes 0..11 for a chord symbol like 'Bm7b5'.

    Chord tones are ordered from the root (root, third, fifth, seventh); the
    scale is sorted ascending from C.

    The scale is a pragmatic choice per chord quality: dominant -> mixolydian,
    minor 7 -> dorian, half-diminished -> locrian, major -> ionian (or lydian
    when the chord is not the key's tonic). Good enough to comp and solo on.
    """
    k = (symbol, key_name)
    if k in _chord_cache:
        return _chord_cache[k]
    sym = symbol.replace("maj7", "M7").replace("Δ", "M7")
    # jazz spelling "Eb" -> music21 spelling "E-" for the root's flat (alterations like b5 stay)
    if len(sym) > 1 and sym[1] == "b":
        sym = sym[0] + "-" + sym[2:]
    cs = harmony.ChordSymbol(sym)
    root = cs.root().pitchClass
    # chord tones ordered from the root upward: root, third, fifth, seventh
    tones = tuple(sorted({p.pitchClass for p in cs.pitches}, key=lambda pc: (pc - root) % 12))
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
            elif it.startswith("free"):
                bars = int(it.split(":", 1)[1]) if ":" in it else 0
                out.append(Section("free", tuple(roles), bars))
            elif it.startswith("solo:"):
                out.append(Section("solo", (it.split(":", 1)[1],), 0))
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


_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_QUALITIES = {"m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11), "7": (0, 4, 7, 10)}
# every minor seventh, major seventh and dominant at every root: enough for the standards this
# band plays, and it copes with an arrangement that modulates
CHORD_VOCAB = {f"{_NAMES[r]}{q}": tuple((r + i) % 12 for i in ivs)
               for r in range(12) for q, ivs in _QUALITIES.items()}


def _load_arrangement(path: Path, doc: dict) -> dict:
    """Read a multi-track MIDI arrangement into parts per role, plus tempo, meter, bars and,
    unless the file gives a chart, a chord estimate per half-bar from the bass and chords."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(path))
    times, tempos = pm.get_tempo_changes()
    # the tempo that holds for most of the file wins (a count-in is often at another tempo), and
    # the grid starts where it begins unless the tune says otherwise
    if len(tempos):
        spans = [(float(times[i + 1]) if i + 1 < len(times) else pm.get_end_time()) - float(times[i]) for i in range(len(times))]
        dom = int(np.argmax(spans))
        file_bpm, file_t0 = float(tempos[dom]), float(times[dom])
    else:
        file_bpm, file_t0 = 120.0, 0.0
    bpm = float(doc.get("tempo_bpm") or file_bpm)
    ts = pm.time_signature_changes
    beats = int(doc.get("meter", f"{ts[0].numerator}/4" if ts else "4/4").split("/")[0])
    beat_s = 60.0 / bpm
    t0 = float(doc.get("grid_offset_s", file_t0))
    n_bars = int(np.ceil((pm.get_end_time() - t0) / (beat_s * beats)))
    by_name: dict[str, list] = {}
    for inst in pm.instruments:
        by_name.setdefault(inst.name, []).append(inst)

    def tracks_for(spec: str) -> list:
        """A part spec: a track name, `track:N` (index among instruments), or `program:N`."""
        if spec.startswith("track:"):
            i = int(spec.split(":", 1)[1])
            return [pm.instruments[i]] if 0 <= i < len(pm.instruments) else []
        if spec.startswith("program:"):
            prog = int(spec.split(":", 1)[1])
            return [inst for inst in pm.instruments if inst.program == prog and not inst.is_drum]
        return by_name.get(spec, [])

    skyline_roles = set(doc.get("skyline") or [])
    parts: dict[str, list[tuple[float, float, int, int]]] = {}
    for role, specs in (doc.get("parts") or {}).items():
        notes = []
        for spec in ([specs] if isinstance(specs, str) else specs):
            for inst in tracks_for(str(spec)):
                for n in inst.notes:
                    if n.start < t0:
                        continue
                    notes.append(((n.start - t0) / beat_s, max(0.05, (n.end - n.start) / beat_s), int(n.pitch), int(n.velocity)))
        notes.sort()
        if role in skyline_roles:
            notes = _skyline(notes)
        parts[role] = notes
    # form: bars where the melody part has notes are "head"; the rest is "vamp" (everyone else
    # still follows their written parts, the soloist rests)
    lead = doc.get("lead", "sax")
    dens = np.zeros(n_bars, int)
    for st, _, _, _ in parts.get(lead, []):
        b = int(st // beats)
        if 0 <= b < n_bars:
            dens[b] += 1
    kinds = ["head" if d >= 3 else "vamp" for d in dens]
    # a rest of a bar or two inside a melody is still the head, not a new section
    i = 0
    while i < len(kinds):
        if kinds[i] == "vamp":
            j = i
            while j < len(kinds) and kinds[j] == "vamp":
                j += 1
            if 0 < i and j < len(kinds) and j - i <= 2:
                for k in range(i, j):
                    kinds[k] = "head"
            i = j
        else:
            i += 1
    form: list[Section] = []
    for k in kinds:
        if form and form[-1].kind == k:
            form[-1] = Section(k, form[-1].who, form[-1].bars + 1)
        else:
            form.append(Section(k, (lead,) if k == "head" else (), 1))
    chart = doc.get("chart") or []
    if not chart:
        chord_insts = [i for spec in (doc.get("chord_tracks") or ["ACOU BASS", "A.PIANO 2"]) for i in tracks_for(str(spec))]
        bass_insts = tracks_for(str(doc.get("bass_track", "ACOU BASS")))
        chart = _estimate_chart(pm, t0, beat_s, beats, n_bars, chord_insts, bass_insts)
    return {"bpm": bpm, "beats": beats, "n_bars": n_bars, "parts": parts, "form": form, "chart": chart,
            "melody": [(st, d, m) for (st, d, m, _v) in parts.get(lead, [])]}


def _skyline(notes: list[tuple[float, float, int, int]]) -> list[tuple[float, float, int, int]]:
    """One line out of several: at any moment keep only the highest note, and cut a note
    short when a higher one starts over it. For a soloist reading a section part."""
    out: list[tuple[float, float, int, int]] = []
    for st, dur, midi, vel in notes:
        end = st + dur
        if out:
            pst, pdur, pmidi, pvel = out[-1]
            pend = pst + pdur
            if st < pend - 1e-6:
                if midi <= pmidi:
                    continue                       # a lower note under a sounding higher one
                out[-1] = (pst, max(0.05, st - pst), pmidi, pvel)   # the higher note takes over
        out.append((st, dur, midi, vel))
    return out


def _estimate_chart(pm, t0: float, beat_s: float, beats: int, n_bars: int, chord_insts: list,
                    bass_insts: list) -> list[list[str]]:
    """Chord per half-bar (3 + 2 in five, 2 + 2 in four) by template match over pitch-class
    time within the window, with the bass root weighted; vocabulary is the tune's own chords."""
    from collections import Counter

    insts = [i for i in chord_insts if not i.is_drum]
    bass = list(bass_insts)
    bass_ids = {id(i) for i in bass}
    roots = {name: pcs[0] for name, pcs in CHORD_VOCAB.items()}

    def window(a: float, b: float) -> str:
        w: Counter = Counter()
        for inst in insts:
            for n in inst.notes:
                if n.start < b and n.end > a:
                    w[n.pitch % 12] += (min(n.end, b) - max(n.start, a)) * (2.0 if id(inst) in bass_ids else 1.0)
        if not w:
            return ""
        bass_pcs: Counter = Counter(n.pitch % 12 for i in bass for n in i.notes if n.start < b and n.end > a)
        best, score = "", -1e9
        for name, pcs in CHORD_VOCAB.items():
            sc = sum(w[p] for p in pcs) - 0.5 * sum(v for p, v in w.items() if p not in pcs)
            if bass_pcs and bass_pcs.most_common(1)[0][0] == roots[name]:
                sc *= 1.4
            if sc > score:
                best, score = name, sc
        return best

    split = 3 if beats == 5 else beats // 2
    rows = []
    for b in range(n_bars):
        a = t0 + b * beats * beat_s
        c1 = window(a, a + split * beat_s)
        c2 = window(a + split * beat_s, a + beats * beat_s)
        row = [""] * beats
        row[0] = c1
        row[split] = c2 if c2 != c1 else ""
        rows.append(row)
    return rows


def load_tune(path: Path) -> Tune:
    path = Path(path)
    doc = yaml.safe_load(path.read_text())
    roles = list(doc.get("roles", []))
    if doc.get("arrangement"):
        arr = _load_arrangement(path.parent / doc["arrangement"], doc)
        return Tune(
            name=doc["name"], tempo_bpm=arr["bpm"], grid=doc.get("grid", "swing8"), meter_beats=arr["beats"],
            key=doc.get("key", "C"), chart=arr["chart"], form=arr["form"], roles=roles,
            coupling=doc.get("coupling", {}), free_style=False, melody=arr["melody"], source_dir=path.parent,
            parts=arr["parts"], arrangement=doc["arrangement"], written=str(doc.get("written", "gated")),
        )
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
    meter = str(doc.get("meter", "4/4"))
    beats = int(meter.split("/")[0])
    if meter.split("/")[1] != "4":
        raise ValueError(f"meter {meter}: only quarter-note beats are supported")
    return Tune(
        name=doc["name"], tempo_bpm=float(doc.get("tempo_bpm", 120)), grid=doc.get("grid", "swing8"),
        meter_beats=beats,
        key=doc.get("key", "C"), chart=chart, form=filled, roles=roles,
        coupling=doc.get("coupling", {}), free_style=bool(doc.get("free_style", False)),
        melody=melody, source_dir=path.parent,
    )
