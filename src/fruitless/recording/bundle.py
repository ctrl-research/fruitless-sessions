"""Assemble a take bundle: what the stage loads.

    <bundle>/
      take.json                 manifest (format, name, duration, flies, shared files, provenance)
      shared/soma-xyz.bin       float32[N, 3] soma position per pack index, voxels (8 nm); NaN when unknown
      shared/superclass.bin     uint8[N] code per pack index; legend in take.json
      <role>/soma/              FSA1 layer, whole brain
      <role>/hero/              FSA1 layer, role circuit (subset.npy maps to pack indices)
      mix.ogg, <role>.mid       once there is music (phase 2)

Positions are stored per pack index so a layer's neuron field indexes straight
into the position array. The stage never sees a bodyId.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from fruitless import __version__, paths
from fruitless.data import annotations as ann
from fruitless.data.sources import load_lock

FORMAT = "fruitless-take/1"


def soma_xyz_by_index(neuron_ids: np.ndarray) -> np.ndarray:
    """float32[N, 3] in pack order, NaN where the annotation has no soma."""
    ids, xyz = ann.soma_xyz()
    out = np.full((neuron_ids.size, 3), np.nan, dtype=np.float32)
    pos = np.searchsorted(neuron_ids, ids)
    pos = np.minimum(pos, neuron_ids.size - 1)
    ok = neuron_ids[pos] == ids
    out[pos[ok]] = xyz[ok]
    return out


def superclass_by_index(neuron_ids: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """uint8[N] code per pack index and the legend (code -> superclass name). 255 = none."""
    t = ann.neurons()
    body = t["bodyId"].to_numpy().astype(np.int64)
    sc = t["superclass"].to_pylist()
    legend = sorted({s for s in sc if s is not None})
    code_of = {s: i for i, s in enumerate(legend)}
    codes_rows = np.array([code_of.get(s, 255) for s in sc], dtype=np.uint8)
    order = np.argsort(body, kind="stable")
    at = np.searchsorted(body[order], neuron_ids)
    at = np.minimum(at, body.size - 1)
    out = np.full(neuron_ids.size, 255, dtype=np.uint8)
    ok = body[order][at] == neuron_ids
    out[ok] = codes_rows[order][at][ok]
    return out, legend


@dataclass
class FlySpec:
    role: str
    layers: dict[str, Path]           # layer name -> directory holding activity.json
    circuit: dict[str, list[int]] = field(default_factory=dict)   # group -> pack indices
    files: dict[str, Path] = field(default_factory=dict)          # published name -> source file
    extra: dict = field(default_factory=dict)                     # motor, notes, midi entries


def write_shared(bundle: Path, pack) -> dict:
    """Soma positions and superclass codes are the same for every take, so they live once in
    `<takes root>/shared/` and bundles point at them with a `../shared/` path."""
    shared = bundle.parent / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    xyz_path, sc_path = shared / "soma-xyz.bin", shared / "superclass.bin"
    codes, legend = superclass_by_index(pack.neuron_ids)
    if not xyz_path.is_file():
        xyz = soma_xyz_by_index(pack.neuron_ids)
        xyz_path.write_bytes(xyz.astype("<f4").tobytes())
    if not sc_path.is_file():
        sc_path.write_bytes(codes.tobytes())
    xyz = np.frombuffer(xyz_path.read_bytes(), dtype="<f4").reshape(-1, 3)
    return {
        "soma_xyz": "../shared/soma-xyz.bin",
        "superclass": "../shared/superclass.bin",
        "superclass_legend": legend,
        "n_neurons": int(pack.n_neurons),
        "with_soma": int(np.isfinite(xyz[:, 0]).sum()),
        "voxel_nm": 8,
    }


def write_bundle(bundle: Path, name: str, pack, flies: list[FlySpec], duration_s: float,
                 seed: int | None, extra: dict | None = None, audio_src: Path | None = None) -> dict:
    bundle = Path(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
    audio = None
    if audio_src is not None and Path(audio_src).is_file():
        shutil.copy2(audio_src, bundle / Path(audio_src).name)
        audio = Path(audio_src).name
    shared = write_shared(bundle, pack)
    fly_entries = []
    for f in flies:
        layers = {}
        for lname, src in f.layers.items():
            dst = bundle / f.role / lname
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            meta = json.loads((dst / "activity.json").read_text())
            layers[lname] = {"path": f"{f.role}/{lname}", **meta}
        for pub, src in f.files.items():
            dst = bundle / f.role / pub
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        fly_entries.append({"role": f.role, "layers": layers, "circuit": f.circuit, **f.extra})
    manifest = {
        "format": FORMAT,
        "name": name,
        "duration_s": duration_s,
        "seed": seed,
        "flies": fly_entries,
        "shared": shared,
        "audio": audio,
        "provenance": {
            "fruitless": __version__,
            "pack_dataset": pack.manifest.get("dataset"),
            "pack_arrays_sha256": {k: v["sha256"] for k, v in pack.manifest["arrays"].items()},
            "sources": {k: {"name": s.name, "sha256": s.sha256} for k, s in load_lock().items()},
            "engine": pack.manifest.get("semantics", {}).get("weight_application"),
        },
        **(extra or {}),
    }
    # keep a meshes entry from an earlier `fruitless meshes` run on this bundle
    old = bundle / "take.json"
    if old.is_file() and (bundle / "meshes.json").is_file():
        prev = json.loads(old.read_text())
        if "meshes" in prev:
            manifest["meshes"] = prev["meshes"]
    old.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def default_stage_dir() -> Path:
    return paths.ROOT / "stage" / "public" / "takes"


def write_index(stage_takes: Path) -> list[dict]:
    """List every bundle under the stage's takes directory for the page's dropdown."""
    stage_takes = Path(stage_takes)
    entries = []
    for d in sorted(p for p in stage_takes.iterdir() if (p / "take.json").is_file()):
        m = json.loads((d / "take.json").read_text())
        entries.append({
            "name": m["name"], "path": d.name, "duration_s": m.get("duration_s", 0),
            "roles": [f["role"] for f in m.get("flies", [])],
            "iterations": m.get("iterations", 1),
            "tune": (m.get("tune") or {}).get("name"),
            "audio": bool(m.get("audio")),
        })
    (stage_takes / "index.json").write_text(json.dumps(entries, indent=2) + "\n")
    return entries


def flies_from_take_dir(take: Path) -> tuple[list[FlySpec], dict, str | None]:
    """Read a take directory written by `fruitless take` (take.json) or `fruitless smoke`
    (smoke.json) and describe its flies. Returns (flies, extra manifest fields, audio file)."""
    take = Path(take)
    if (take / "take.json").is_file():
        rep = json.loads((take / "take.json").read_text())
        flies = []
        for f in rep["flies"]:
            role = f["role"]
            layers = {k: take / role / k for k in f["layers"]}
            files = {}
            extra = {}
            if "motor" in f:
                files["motor.bin"] = take / f["motor"]["file"]
                extra["motor"] = {**f["motor"], "file": f"{role}/motor.bin"}
            if "notes" in f:
                files["notes.json"] = take / f["notes"]
                extra["notes"] = f"{role}/notes.json"
            if "midi" in f:
                files[f"{role}.mid"] = take / f["midi"]
                extra["midi"] = f"{role}/{role}.mid"
            extra["n_notes"] = f.get("n_notes", 0)
            if "mesh_groups" in f:
                extra["mesh_groups"] = f["mesh_groups"]
            else:
                # takes recorded before mesh_groups existed: take the fly class's definition
                from fruitless.conductor.take import FLIES
                if role in FLIES:
                    extra["mesh_groups"] = list(FLIES[role]().mesh_groups)
            flies.append(FlySpec(role, layers, f.get("circuit", {}), files, extra))
        extra_manifest = {"tune": rep.get("tune"), "seconds_wall": rep.get("seconds_wall"),
                          "total_spikes": rep.get("total_spikes"), "drive": rep.get("drive"),
                          "iterations": rep.get("iterations", 1), "free_keys": rep.get("free_keys")}
        return flies, extra_manifest, rep.get("audio")
    if (take / "smoke.json").is_file():
        rep = json.loads((take / "smoke.json").read_text())
        layers = {d.name: d for d in take.iterdir() if (d / "activity.json").is_file()}
        return [FlySpec("smoke", layers, rep.get("circuit", {}))], {"smoke": rep, "iterations": rep.get("iterations", 1)}, None
    raise FileNotFoundError(f"{take}: no take.json or smoke.json")
