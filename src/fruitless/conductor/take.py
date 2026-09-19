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
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from fruitless import paths
from fruitless.conductor.mapper import SaxMapper
from fruitless.conductor.mappers import BassMapper, DrumsMapper, PianoMapper, key_from_bump
from fruitless.conductor.midi import write_midi, write_notes_json
from fruitless.conductor.tune import Tune, chord_pitch_classes, load_tune
from fruitless.flies.base import Fly
from fruitless.flies.bass import TRIPOD_A, TRIPOD_B, Bass
from fruitless.flies.drums import Drums
from fruitless.flies.piano import Piano
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
EPG_KEY_HZ = 60.0      # piano: the chord root's wedge
EPG_BG_HZ = 6.0        # piano: the other wedges
PEN_DRIFT_HZ = 40.0    # piano, free style: ear imbalance pushes PEN_a left or right
PAM_REWARD_HZ = 50.0   # mushroom body: reward when the soloist lands a chord tone on a beat
PPL1_PUNISH_HZ = 50.0  # punishment when it lands a clash
FLIES = {"sax": Sax, "bass": Bass, "drums": Drums, "piano": Piano}
MAPPERS = {"sax": SaxMapper, "bass": BassMapper, "drums": DrumsMapper, "piano": PianoMapper}
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


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
        mixed = synth.mix(tracks, gains={"sax": 1.0, "bass": 0.9, "drums": 0.7, "piano": 0.75})
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
    rep["iterations"] = int(rep.get("iterations", 0)) + 1
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
    # a grid step is a whole number of 0.1 ms ticks; at 178 BPM a swing eighth is 168.54 ms,
    # so rounding to milliseconds would drift the music against the brains by 0.3 %
    step_ticks = round(tune.step_seconds * 1000 * TICKS_PER_MS)
    drift = abs(step_ticks / TICKS_PER_MS / 1000 - tune.step_seconds) * tune.total_steps
    if drift > 0.005:
        print(f"note: grid rounding drifts {drift * 1000:.1f} ms over the take", file=sys.stderr)
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
    free_keys: list[str | None] = []
    for step in range(tune.total_steps):
        sec, _ = tune.section_at(step)
        beat_step = step % tune.steps_per_beat
        beat = (step % tune.steps_per_bar) // tune.steps_per_beat
        new_readouts: dict[str, dict[str, float]] = {}
        # consonance of the soloist's most recent note against the chord, for the mushroom body
        consonance: dict[str, str | None] = {"verdict": None}
        soloist = tune.soloist_at(step)
        chord_now = tune.chord_at(step)
        if soloist in mappers and chord_now is not None and beat_step == 0:
            last = getattr(mappers[soloist], "_open", None) or (mappers[soloist].notes[-1] if mappers[soloist].notes else None)
            if last is not None and step - last.step <= tune.steps_per_beat:
                tones, scale = chord_pitch_classes(chord_now, tune.key)
                pc = last.midi % 12
                consonance["verdict"] = "reward" if pc in tones else ("punish" if pc not in scale else None)
        # free style: the piano's bump names the key at every bar line; the tune's key seeds bar 1
        if tune.free_style and step == 0:
            tune.free_chord = f"{tune.key}7"
        if tune.free_style and "piano" in last_readouts and step % tune.steps_per_bar == 0 and step > 0:
            pr = last_readouts["piano"]
            if pr.get("bump_mag", 0.0) > 0.1 and pr.get("epg_hz", 0.0) > 1.0:
                tune.free_chord = f"{NAMES[key_from_bump(pr['bump_deg'])]}7"
        if step % tune.steps_per_bar == 0:
            free_keys.append(tune.free_chord if tune.free_style else None)   # after this bar's key is set
        for role, fly in flies.items():
            s = sessions[role]
            rates = np.zeros((1, s.drivable.size))
            pos = {int(i): k for k, i in enumerate(s.drivable)}
            set_rate = functools.partial(_set_rate, fly, rates, pos)

            # role drive
            if role == "sax":
                if sec.kind == "head":
                    rate = PC1_NOTE_HZ if tune.melody_at(step) is not None else PC1_REST_HZ
                elif sec.kind in ("solo", "free") and tune.soloist_at(step) == role:
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
            elif role == "piano":
                chord = tune.chord_at(step)
                if chord is not None and tune.chart:
                    root = chord_pitch_classes(chord, tune.key)[0][0]
                    key_wedge = Piano.wedge_for_pitch_class(root)
                    for w in range(1, 9):
                        set_rate(f"epg_w{w}", EPG_KEY_HZ if w == key_wedge else EPG_BG_HZ)
                else:
                    # free style: no landmark. The ring is held on the key it named last bar
                    # (a weaker drive than a chart gives) while the ear imbalance pushes PEN_a
                    # left or right, so the key can wander from bar to bar.
                    cur = tune.free_chord or f"{tune.key}7"
                    cur_wedge = Piano.wedge_for_pitch_class(chord_pitch_classes(cur, tune.key)[0][0])
                    for w in range(1, 9):
                        set_rate(f"epg_w{w}", EPG_KEY_HZ * 0.55 if w == cur_wedge else EPG_BG_HZ * 2)
                    ca, cb = heard(tune, role, last_readouts)
                    bal = (ca - cb) / max(1.0, ca + cb)
                    set_rate("pen_a_L", PEN_DRIFT_HZ * max(0.0, bal))
                    set_rate("pen_a_R", PEN_DRIFT_HZ * max(0.0, -bal))
                # mushroom body teaching signal from what the soloist just played
                verdict = consonance.get("verdict")
                set_rate("PAM", PAM_REWARD_HZ if verdict == "reward" else 0.0)
                set_rate("PPL1", PPL1_PUNISH_HZ if verdict == "punish" else 0.0)

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
    # a fingerprint of every fly's per-neuron spike counts: same seed, tune, pack and engine give
    # the same digest, so a take can be checked for reproducibility without the recordings
    counts_sha256 = {role: hashlib.sha256(np.ascontiguousarray(sessions[role].total_counts().astype(np.int32)).tobytes()).hexdigest()
                     for role in flies}

    # ------------------------------------------------------------ outputs
    manifest_flies, audio = write_outputs(out, tune, flies, mappers, seed, render_audio,
                                          layers_by_role={role: {k: w.close() for k, w in writers[role].items()} for role in flies},
                                          motor_by_role={role: np.stack(motor[role]).astype("<f4") for role in flies})

    prev = json.loads((out / "take.json").read_text()) if (out / "take.json").is_file() else {}
    report = {
        "iterations": int(prev.get("iterations", 0)) + 1,   # runs of `take` and `remap` on this take
        "tune": {
            "name": tune.name, "tempo_bpm": tune.tempo_bpm, "grid": tune.grid, "key": tune.key,
            "step_s": tune.step_seconds, "steps_per_bar": tune.steps_per_bar,
            "beats_per_bar": tune.beats_per_bar, "meter": f"{tune.beats_per_bar}/4",
            "total_steps": tune.total_steps, "duration_s": tune.duration_s,
            "chart": tune.chart,
            "form": [{"kind": s.kind, "who": list(s.who), "bars": s.bars} for s in tune.form],
            "free_style": tune.free_style,
        },
        "seed": seed,
        "free_keys": free_keys if tune.free_style else None,
        "seconds_bio": tune.duration_s,
        "seconds_wall": round(wall, 1),
        "total_spikes": total_spikes,
        "counts_sha256": counts_sha256,
        "audio": audio,
        "flies": manifest_flies,
        "drive": {"pc1_note_hz": PC1_NOTE_HZ, "pc1_rest_hz": PC1_REST_HZ, "pc1_solo_hz": PC1_SOLO_HZ,
                  "ear_hz": EAR_HZ, "pool_hz": POOL_HZ, "pool_off_hz": POOL_OFF_HZ, "dna02_hz": DNA02_HZ,
                  "couple_hz": COUPLE_HZ, "coupling": tune.coupling, "epg_key_hz": EPG_KEY_HZ,
                  "pen_drift_hz": PEN_DRIFT_HZ, "pam_reward_hz": PAM_REWARD_HZ, "ppl1_punish_hz": PPL1_PUNISH_HZ},
    }
    (out / "take.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
