"""Notes to a MIDI file and to the JSON the stage reads."""

from __future__ import annotations

import json
from pathlib import Path

import pretty_midi

from fruitless.conductor.mapper import Note

PROGRAMS = {"sax": 66, "bass": 33, "piano": 0, "drums": 0}   # GM: tenor sax, fingered bass, piano


def write_midi(path: Path, notes: list[Note], role: str, tempo_bpm: float) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo_bpm)
    inst = pretty_midi.Instrument(program=PROGRAMS.get(role, 0), is_drum=(role == "drums"), name=role)
    for n in notes:
        inst.notes.append(pretty_midi.Note(velocity=n.vel, pitch=n.midi, start=n.t, end=n.t + n.dur))
    pm.instruments.append(inst)
    pm.write(str(path))


def write_notes_json(path: Path, notes: list[Note]) -> None:
    path.write_text(json.dumps([
        {"t": round(n.t, 4), "dur": round(n.dur, 4), "midi": n.midi, "vel": n.vel,
         "step": n.step, "source": n.source} for n in notes
    ]) + "\n")
