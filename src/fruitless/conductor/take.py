"""The studio take: run the flies through a tune, record everything, render.

For each grid step the conductor decides every fly's external drive, advances
each fly's Session by the step's ticks, records spikes to the activity layers,
computes the fly's motor readout, and hands it to the mapper. At the end it
writes MIDI, renders audio, and assembles the take bundle for the stage.

Drive for the soloist in a head section follows the melody: a high pC1 rate
while a melody note is sounding, a low one on rests, so the fly's song circuit
is asked to sing where the tune has notes. What comes out of the wing motor
neurons is the fly's. In solo sections the drive is a steady mid rate and the
readout's variation is the network's own. The head is also played into the
fly's ears as Poisson input on JO-A (upper) and JO-B (lower) afferents.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from fruitless import paths
from fruitless.conductor.mapper import SaxMapper
from fruitless.conductor.midi import write_midi, write_notes_json
from fruitless.conductor.tune import Tune, load_tune
from fruitless.flies.base import Fly
from fruitless.flies.sax import Sax
from fruitless.flies.select import Resolver
from fruitless.recording.activity import ActivityWriter
from fruitless.render import synth
from fruitless.sim.constants import TICKS_PER_MS
from fruitless.sim.session import Session, poisson_draws

PC1_NOTE_HZ = 60.0     # drive while a melody note sounds
PC1_REST_HZ = 8.0      # drive on rests
PC1_SOLO_HZ = 45.0     # steady drive in the fly's own solo
EAR_HZ = 60.0          # the head into the ears, scaled by melody register
FLIES = {"sax": Sax}


def ear_rates(tune: Tune, step: int, jo_a: int, jo_b: int) -> tuple[float, float]:
    """Rates for JO-A (higher frequencies) and JO-B (lower) from the melody note now playing."""
    m = tune.melody_at(step)
    if m is None:
        return 0.0, 0.0
    hi = float(np.clip((m - 55) / 24.0, 0.0, 1.0))
    return EAR_HZ * hi, EAR_HZ * (1.0 - hi)


def run_take(tune_path: Path, out: Path, seed: int = 0, pack_dir: Path = paths.PACK,
             bin_ms: int = 50, chunk_s: float = 10.0, render_audio: bool = True) -> dict:
    from lif import core

    tune = load_tune(tune_path)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pack = core.load_pack(pack_dir)
    r = Resolver(pack.neuron_ids)
    step_ticks = round(tune.step_seconds * 1000) * TICKS_PER_MS
    if abs(step_ticks / TICKS_PER_MS / 1000 - tune.step_seconds) > 1e-9:
        print(f"note: step {tune.step_seconds}s rounded to {step_ticks} ticks", file=sys.stderr)
    rng = np.random.default_rng(seed)

    flies: dict[str, Fly] = {}
    sessions: dict[str, Session] = {}
    writers: dict[str, dict[str, ActivityWriter]] = {}
    motor: dict[str, list[np.ndarray]] = {}
    mappers = {}
    for role in tune.roles:
        fly = FLIES[role]()
        fly.resolve(r)
        flies[role] = fly
        sessions[role] = Session(pack, fly.drivable(), edge_split=1)
        (out / role).mkdir(exist_ok=True)
        writers[role] = {
            "soma": ActivityWriter(out / role / "soma", bin_ms, chunk_s, pack.n_neurons),
            "hero": ActivityWriter(out / role / "hero", 10, chunk_s, pack.n_neurons, subset=fly.hero_indices()),
        }
        motor[role] = []
        mappers[role] = SaxMapper(tune, role)   # phase 2: only the sax exists
        print(f"{role}: {fly.hero_indices().size} hero neurons, {fly.drivable().size} drivable", file=sys.stderr)

    t_wall = time.perf_counter()
    total_spikes = 0
    for step in range(tune.total_steps):
        sec, _ = tune.section_at(step)
        for role, fly in flies.items():
            s = sessions[role]
            rates = np.zeros((1, s.drivable.size))
            pos = {int(i): k for k, i in enumerate(s.drivable)}
            # role drive
            if role == "sax":
                if sec.kind == "head":
                    rate = PC1_NOTE_HZ if tune.melody_at(step) is not None else PC1_REST_HZ
                elif sec.kind == "solo" and tune.soloist_at(step) == role:
                    rate = PC1_SOLO_HZ
                else:
                    rate = PC1_REST_HZ
                for i in fly.indices("pC1"):
                    rates[0, pos[int(i)]] = rate
            # ears hear the head
            a_hz, b_hz = ear_rates(tune, step, 0, 0)
            for i in fly.indices("jo_a"):
                rates[0, pos[int(i)]] = a_hz
            for i in fly.indices("jo_b"):
                rates[0, pos[int(i)]] = b_hz
            draws = poisson_draws(rates, step_ticks, rng)
            res = s.step(draws)
            total_spikes += int(res.counts.sum())
            writers[role]["soma"].add(res.events, step_ticks)
            writers[role]["hero"].add(res.events, step_ticks)
            ro = fly.readout(res.counts, res.events, res.t0, step_ticks)
            motor[role].append(ro.values)
            mappers[role].on_step(step, ro.as_dict())
        if step % tune.steps_per_bar == 0:
            bar = step // tune.steps_per_bar
            el = time.perf_counter() - t_wall
            print(f"  bar {bar + 1:3d}/{tune.total_bars} {sec.kind:5s} {el:6.1f}s wall  spikes {total_spikes:,}", file=sys.stderr)
    wall = time.perf_counter() - t_wall

    # ------------------------------------------------------------ outputs
    manifest_flies = []
    tracks = {}
    for role, fly in flies.items():
        layers = {k: w.close() for k, w in writers[role].items()}
        m = np.stack(motor[role]).astype("<f4")
        (out / role / "motor.bin").write_bytes(m.tobytes())
        notes = mappers[role].finish(tune.duration_s)
        write_midi(out / role / f"{role}.mid", notes, role, tune.tempo_bpm)
        write_notes_json(out / role / "notes.json", notes)
        tracks[role] = synth.render(notes, role, tune.duration_s, seed)
        manifest_flies.append({
            "role": role, "layers": layers, "circuit": fly.circuit_json(),
            "mesh_groups": list(fly.mesh_groups),
            "motor": {"file": f"{role}/motor.bin", "names": list(fly.readout_names), "steps": int(m.shape[0])},
            "notes": f"{role}/notes.json", "midi": f"{role}/{role}.mid", "n_notes": len(notes),
        })
        print(f"{role}: {len(notes)} notes", file=sys.stderr)

    audio = None
    if render_audio and tracks:
        mixed = synth.mix(tracks)
        synth.write_wav(out / "mix.wav", mixed)
        enc = synth.encode(out / "mix.wav", out / "mix")
        audio = enc.name if enc else "mix.wav"

    report = {
        "tune": {
            "name": tune.name, "tempo_bpm": tune.tempo_bpm, "grid": tune.grid, "key": tune.key,
            "step_s": tune.step_seconds, "steps_per_bar": tune.steps_per_bar,
            "total_steps": tune.total_steps, "duration_s": tune.duration_s,
            "chart": tune.chart,
            "form": [{"kind": s.kind, "who": list(s.who), "bars": s.bars} for s in tune.form],
            "free_style": tune.free_style,
        },
        "seed": seed,
        "seconds_bio": tune.duration_s,
        "seconds_wall": round(wall, 1),
        "total_spikes": total_spikes,
        "audio": audio,
        "flies": manifest_flies,
        "drive": {"pc1_note_hz": PC1_NOTE_HZ, "pc1_rest_hz": PC1_REST_HZ, "pc1_solo_hz": PC1_SOLO_HZ, "ear_hz": EAR_HZ},
    }
    (out / "take.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
