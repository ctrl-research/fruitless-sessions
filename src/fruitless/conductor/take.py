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

import functools
import json
import sys
import time
from pathlib import Path

import numpy as np

from fruitless import paths
from fruitless.conductor.mapper import SaxMapper
from fruitless.conductor.mappers import BassMapper, DrumsMapper
from fruitless.conductor.midi import write_midi, write_notes_json
from fruitless.conductor.tune import Tune, load_tune
from fruitless.flies.base import Fly
from fruitless.flies.bass import TRIPOD_A, TRIPOD_B, Bass
from fruitless.flies.drums import Drums
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
POOL_HZ = 60.0         # bass: premotor pool of the stepping tripod
POOL_OFF_HZ = 4.0      # bass: the other tripod
DNA02_HZ = 70.0        # drums: steady steering drive
COUPLE_HZ = 80.0       # ear rate at coupling gain 1 and full intensity
FLIES = {"sax": Sax, "bass": Bass, "drums": Drums}
MAPPERS = {"sax": SaxMapper, "bass": BassMapper, "drums": DrumsMapper}


def _set_rate(fly: Fly, rates: np.ndarray, pos: dict[int, int], group: str, hz: float) -> None:
    for i in fly.indices(group):
        rates[0, pos[int(i)]] = hz


def heard(tune: Tune, role: str, last_readouts: dict[str, dict[str, float]]) -> tuple[float, float]:
    """What `role` hears from the others this step, as JO-A / JO-B rates.

    Loudness of a source is its motor intensity normalised to 80 Hz; register
    splits it between the high (JO-A) and low (JO-B) afferents: sax is high,
    drums middle, bass low. Gains come from the tune's coupling matrix.
    """
    a = b = 0.0
    for src, gain in tune.coupling.get(role, {}).items():
        ro = last_readouts.get(src)
        if not ro:
            continue
        if src == "sax":
            loud, hi = ro.get("intensity", 0.0) / 80.0 * ro.get("song_on", 0.0), 0.8
        elif src == "drums":
            loud, hi = (ro.get("power", 0.0) + ro.get("steer", 0.0)) / 160.0, 0.5
        else:
            loud, hi = ro.get("load", 0.0) / 60.0, 0.15
        loud = float(np.clip(loud, 0.0, 1.0)) * float(gain) * COUPLE_HZ
        a += loud * hi
        b += loud * (1.0 - hi)
    return a, b


def ear_rates(tune: Tune, step: int, jo_a: int, jo_b: int) -> tuple[float, float]:
    """Rates for JO-A (higher frequencies) and JO-B (lower) from the melody note now playing."""
    m = tune.melody_at(step)
    if m is None:
        return 0.0, 0.0
    hi = float(np.clip((m - 55) / 24.0, 0.0, 1.0))
    return EAR_HZ * hi, EAR_HZ * (1.0 - hi)


def write_outputs(out: Path, tune: Tune, flies: dict[str, Fly], mappers: dict, seed: int,
                  render_audio: bool, layers_by_role: dict, motor_by_role: dict) -> tuple[list[dict], str | None]:
    """Write motor, notes, MIDI and audio for every fly; returns (fly manifest entries, audio file)."""
    manifest_flies = []
    tracks = {}
    for role, fly in flies.items():
        m = motor_by_role[role]
        (out / role).mkdir(exist_ok=True)
        (out / role / "motor.bin").write_bytes(m.tobytes())
        notes = mappers[role].finish(tune.duration_s)
        write_midi(out / role / f"{role}.mid", notes, role, tune.tempo_bpm)
        write_notes_json(out / role / "notes.json", notes)
        tracks[role] = synth.render(notes, role, tune.duration_s, seed)
        manifest_flies.append({
            "role": role, "layers": layers_by_role[role], "circuit": fly.circuit_json(),
            "mesh_groups": list(fly.mesh_groups),
            "motor": {"file": f"{role}/motor.bin", "names": list(fly.readout_names), "steps": int(m.shape[0])},
            "notes": f"{role}/notes.json", "midi": f"{role}/{role}.mid", "n_notes": len(notes),
        })
        print(f"{role}: {len(notes)} notes", file=sys.stderr)
    audio = None
    if render_audio and tracks:
        mixed = synth.mix(tracks, gains={"sax": 1.0, "bass": 0.9, "drums": 0.7})
        synth.write_wav(out / "mix.wav", mixed)
        enc = synth.encode(out / "mix.wav", out / "mix")
        audio = enc.name if enc else "mix.wav"
    return manifest_flies, audio


def remap(take_dir: Path, tune_path: Path | None = None, render_audio: bool = True) -> dict:
    """Re-run the mappers and the audio render from a take's recorded motor readouts.

    The simulation is untouched; only the music changes. This is how mapping
    rules are iterated without paying for the brains again."""
    take_dir = Path(take_dir)
    rep = json.loads((take_dir / "take.json").read_text())
    tune = load_tune(tune_path or (paths.TUNES / rep["tune"]["name"] / "tune.yaml"))
    flies: dict[str, Fly] = {}
    mappers = {}
    motor_by_role = {}
    layers_by_role = {}
    for f in rep["flies"]:
        role = f["role"]
        fly = FLIES[role]()
        fly._idx = {k: np.array(v, dtype=np.int32) for k, v in f["circuit"].items()}   # from the recorded take
        flies[role] = fly
        mappers[role] = MAPPERS[role](tune, role)
        names = f["motor"]["names"]
        m = np.frombuffer((take_dir / f["motor"]["file"]).read_bytes(), dtype="<f4").reshape(-1, len(names))
        motor_by_role[role] = m
        layers_by_role[role] = f["layers"]
        for step in range(m.shape[0]):
            mappers[role].on_step(step, dict(zip(names, m[step].tolist(), strict=True)))
    manifest_flies, audio = write_outputs(take_dir, tune, flies, mappers, rep.get("seed", 0), render_audio,
                                          layers_by_role, motor_by_role)
    rep["flies"] = manifest_flies
    rep["audio"] = audio
    (take_dir / "take.json").write_text(json.dumps(rep, indent=2) + "\n")
    return rep


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
        fly.resolve(r, pack)
        flies[role] = fly
        sessions[role] = Session(pack, fly.drivable(), edge_split=1)
        (out / role).mkdir(exist_ok=True)
        writers[role] = {
            "soma": ActivityWriter(out / role / "soma", bin_ms, chunk_s, pack.n_neurons),
            "hero": ActivityWriter(out / role / "hero", 10, chunk_s, pack.n_neurons, subset=fly.hero_indices()),
        }
        motor[role] = []
        mappers[role] = MAPPERS[role](tune, role)
        print(f"{role}: {fly.hero_indices().size} hero neurons, {fly.drivable().size} drivable", file=sys.stderr)

    t_wall = time.perf_counter()
    total_spikes = 0
    last_readouts: dict[str, dict[str, float]] = {}
    for step in range(tune.total_steps):
        sec, _ = tune.section_at(step)
        beat_step = step % tune.steps_per_beat
        beat = (step % tune.steps_per_bar) // tune.steps_per_beat
        new_readouts: dict[str, dict[str, float]] = {}
        for role, fly in flies.items():
            s = sessions[role]
            rates = np.zeros((1, s.drivable.size))
            pos = {int(i): k for k, i in enumerate(s.drivable)}
            set_rate = functools.partial(_set_rate, fly, rates, pos)

            # role drive
            if role == "sax":
                if sec.kind == "head":
                    rate = PC1_NOTE_HZ if tune.melody_at(step) is not None else PC1_REST_HZ
                elif sec.kind == "solo" and tune.soloist_at(step) == role:
                    rate = PC1_SOLO_HZ
                else:
                    rate = PC1_REST_HZ
                set_rate("pC1", rate)
            elif role == "bass":
                # the conductor's gait: tripod A steps on beats 1 and 3, B on 2 and 4,
                # each pool driven for the first half of its beat
                stepping = TRIPOD_A if beat % 2 == 0 else TRIPOD_B
                on = beat_step < max(1, tune.steps_per_beat // 2)
                for leg in TRIPOD_A + TRIPOD_B:
                    set_rate(f"pool_{leg}", POOL_HZ if (leg in stepping and on) else POOL_OFF_HZ)
            elif role == "drums":
                set_rate("DNa02", DNA02_HZ)

            # ears: the head (for everyone, in head sections) plus what the others played last step
            a_hz, b_hz = ear_rates(tune, step, 0, 0)
            ca, cb = heard(tune, role, last_readouts)
            set_rate("jo_a", min(200.0, a_hz + ca))
            set_rate("jo_b", min(200.0, b_hz + cb))

            draws = poisson_draws(rates, step_ticks, rng)
            res = s.step(draws)
            total_spikes += int(res.counts.sum())
            writers[role]["soma"].add(res.events, step_ticks)
            writers[role]["hero"].add(res.events, step_ticks)
            ro = fly.readout(res.counts, res.events, res.t0, step_ticks)
            motor[role].append(ro.values)
            d = ro.as_dict()
            new_readouts[role] = d
            mappers[role].on_step(step, d)
        last_readouts = new_readouts
        if step % tune.steps_per_bar == 0:
            bar = step // tune.steps_per_bar
            el = time.perf_counter() - t_wall
            print(f"  bar {bar + 1:3d}/{tune.total_bars} {sec.kind:5s} {el:6.1f}s wall  spikes {total_spikes:,}", file=sys.stderr)
    wall = time.perf_counter() - t_wall

    # ------------------------------------------------------------ outputs
    manifest_flies, audio = write_outputs(out, tune, flies, mappers, seed, render_audio,
                                          layers_by_role={role: {k: w.close() for k, w in writers[role].items()} for role in flies},
                                          motor_by_role={role: np.stack(motor[role]).astype("<f4") for role in flies})

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
        "drive": {"pc1_note_hz": PC1_NOTE_HZ, "pc1_rest_hz": PC1_REST_HZ, "pc1_solo_hz": PC1_SOLO_HZ,
                  "ear_hz": EAR_HZ, "pool_hz": POOL_HZ, "pool_off_hz": POOL_OFF_HZ, "dna02_hz": DNA02_HZ,
                  "couple_hz": COUPLE_HZ, "coupling": tune.coupling},
    }
    (out / "take.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
