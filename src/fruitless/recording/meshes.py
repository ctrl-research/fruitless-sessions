"""Hero neuron meshes for the stage, from the MaleCNS precomputed mesh source.

The release ships neuroglancer multi-resolution Draco meshes at
`gs://flyem-male-cns/v1.0/segmentation` (mesh key `multi-res-meshes`), read
here through cloud-volume over public HTTPS with no credentials. LOD 3 is the
coarsest: about 28k vertices for a large motor neuron, small enough that a
few hundred hero neurons fit a static page.

Output is one binary per neuron, in the bundle's `meshes/` directory:

    <pack index>.fsm      magic "FSM2", uint32 n_vertices, uint32 n_triangles, uint32 flags,
                          float32[3] bbox min, float32[3] bbox size (voxels, 8 nm),
                          uint16[n_vertices, 3] positions quantized into the bbox,
                          uint16[n_triangles, 3] indices (flags bit 0 set: uint32 indices)

Quantizing to 16 bits inside the neuron's own bounding box keeps positions to
well under a voxel of error and halves the file against float32; uint16
indices where the mesh allows halve the rest. A 640-neuron circuit at float32
was 180 MB, which a static page cannot carry.

plus `meshes/index.json` listing pack index, bodyId, vertex and triangle
counts and LOD. Positions stay in the same voxel units as the soma layer so the
stage applies one transform to everything.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

SOURCE = "precomputed://https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation"
VOXEL_NM = 8.0
def _volume():
    try:
        from cloudvolume import CloudVolume
    except ImportError as e:  # pragma: no cover
        raise SystemExit("cloud-volume is required: uv sync --extra meshes") from e
    return CloudVolume(SOURCE, use_https=True, progress=False)


MAGIC = b"FSM2"
_HEADER = struct.Struct("<4sIIIffffff")
FLAG_U32_INDICES = 1


def write_fsm(path: Path, vertices_voxels: np.ndarray, faces: np.ndarray) -> None:
    v = np.asarray(vertices_voxels, dtype=np.float64)
    f = np.asarray(faces)
    lo = v.min(axis=0) if v.size else np.zeros(3)
    size = (v.max(axis=0) - lo) if v.size else np.ones(3)
    size = np.where(size > 0, size, 1.0)
    q = np.rint((v - lo) / size * 65535.0).clip(0, 65535).astype("<u2")
    u32 = int(v.shape[0]) > 65535
    idx = np.ascontiguousarray(f, dtype="<u4" if u32 else "<u2")
    with path.open("wb") as fh:
        fh.write(_HEADER.pack(MAGIC, v.shape[0], f.shape[0], FLAG_U32_INDICES if u32 else 0,
                              *map(float, lo), *map(float, size)))
        fh.write(q.tobytes())
        fh.write(idx.tobytes())


def read_fsm(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(float32[nv, 3] positions in voxels, uint32[nf, 3] faces), dequantized."""
    data = Path(path).read_bytes()
    magic, nv, nf, flags, *bb = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"{path}: not an FSM2 mesh")
    lo, size = np.array(bb[:3]), np.array(bb[3:])
    o = _HEADER.size
    q = np.frombuffer(data, dtype="<u2", count=nv * 3, offset=o).reshape(nv, 3)
    o += 6 * nv
    if flags & FLAG_U32_INDICES:
        f = np.frombuffer(data, dtype="<u4", count=nf * 3, offset=o).reshape(nf, 3)
    else:
        f = np.frombuffer(data, dtype="<u2", count=nf * 3, offset=o).reshape(nf, 3)
    v = (q.astype(np.float64) / 65535.0 * size + lo).astype(np.float32)
    return v, f.astype(np.uint32)


def fetch_meshes(bundle: Path, neuron_ids: np.ndarray, indices: np.ndarray, lod: int = 3,
                 overwrite: bool = False, prune: bool = True) -> dict:
    """Fetch and write the meshes of the given pack indices; returns the index document.

    prune removes meshes in the directory that are not in `indices`, so a bundle
    carries exactly its flies' mesh groups."""
    out = Path(bundle) / "meshes"
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    doc = json.loads(index_path.read_text()) if index_path.is_file() else {"lod": lod, "voxel_nm": VOXEL_NM, "neurons": {}}
    if doc.get("format") != "fsm2":
        # older float32 files: refetch everything
        doc = {"lod": lod, "voxel_nm": VOXEL_NM, "format": "fsm2", "neurons": {}}
        for f in out.glob("*.fsm"):
            f.unlink()
    wanted = {str(int(i)) for i in np.unique(np.asarray(indices)).tolist()}
    if prune:
        for key in list(doc["neurons"]):
            if key not in wanted:
                (out / f"{key}.fsm").unlink(missing_ok=True)
                del doc["neurons"][key]
    cv = None
    for i in sorted(int(k) for k in wanted):
        key = str(i)
        path = out / f"{i}.fsm"
        if path.is_file() and key in doc["neurons"] and not overwrite:
            continue
        body = int(neuron_ids[i])
        cv = cv or _volume()
        t = time.perf_counter()
        got = cv.mesh.get(body, lod=lod)
        mesh = got[body] if isinstance(got, dict) else got
        verts = np.asarray(mesh.vertices, dtype=np.float64) / VOXEL_NM   # nm -> voxels
        faces = np.asarray(mesh.faces, dtype=np.uint32)
        write_fsm(path, verts, faces)
        doc["neurons"][key] = {"bodyId": body, "vertices": int(verts.shape[0]),
                               "triangles": int(faces.shape[0]), "file": f"meshes/{i}.fsm",
                               "bytes": path.stat().st_size}
        print(f"  mesh {i:7d} bodyId {body:12d}  {verts.shape[0]:7,d} v {faces.shape[0]:8,d} t  "
              f"{time.perf_counter() - t:.1f}s", file=sys.stderr)
        index_path.write_text(json.dumps(doc, indent=1) + "\n")
    index_path.write_text(json.dumps(doc, indent=1) + "\n")
    return doc
