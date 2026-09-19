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


def write_shared(bundle: Path, pack) -> dict:
    shared = bundle / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    xyz = soma_xyz_by_index(pack.neuron_ids)
    (shared / "soma-xyz.bin").write_bytes(xyz.astype("<f4").tobytes())
    codes, legend = superclass_by_index(pack.neuron_ids)
    (shared / "superclass.bin").write_bytes(codes.tobytes())
    return {
        "soma_xyz": "shared/soma-xyz.bin",
        "superclass": "shared/superclass.bin",
        "superclass_legend": legend,
        "n_neurons": int(pack.n_neurons),
        "with_soma": int(np.isfinite(xyz[:, 0]).sum()),
        "voxel_nm": 8,
    }


def write_bundle(bundle: Path, name: str, pack, flies: list[FlySpec], duration_s: float,
                 seed: int | None, extra: dict | None = None) -> dict:
    bundle = Path(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
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
        fly_entries.append({"role": f.role, "layers": layers, "circuit": f.circuit})
    manifest = {
        "format": FORMAT,
        "name": name,
        "duration_s": duration_s,
        "seed": seed,
        "flies": fly_entries,
        "shared": shared,
        "audio": None,
        "provenance": {
            "fruitless": __version__,
            "pack_dataset": pack.manifest.get("dataset"),
            "pack_arrays_sha256": {k: v["sha256"] for k, v in pack.manifest["arrays"].items()},
            "sources": {k: {"name": s.name, "sha256": s.sha256} for k, s in load_lock().items()},
            "engine": pack.manifest.get("semantics", {}).get("weight_application"),
        },
        **(extra or {}),
    }
    (bundle / "take.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def default_stage_dir() -> Path:
    return paths.ROOT / "stage" / "public" / "takes"
