"""Hero neuron meshes for the stage, from the MaleCNS precomputed mesh source.

The release ships neuroglancer multi-resolution Draco meshes at
`gs://flyem-male-cns/v1.0/segmentation` (mesh key `multi-res-meshes`), read
here through cloud-volume over public HTTPS with no credentials. LOD 3 is the
coarsest: about 28k vertices for a large motor neuron, small enough that a
few hundred hero neurons fit a static page.

Output is one binary per neuron, in the bundle's `meshes/` directory:

    <pack index>.fsm      magic "FSM1", uint32 n_vertices, uint32 n_triangles,
                          float32[n_vertices, 3] positions in MaleCNS voxels (8 nm),
                          uint32[n_triangles, 3] indices

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
MAGIC = b"FSM1"
_HEADER = struct.Struct("<4sII")


def _volume():
    try:
        from cloudvolume import CloudVolume
    except ImportError as e:  # pragma: no cover
        raise SystemExit("cloud-volume is required: uv sync --extra meshes") from e
    return CloudVolume(SOURCE, use_https=True, progress=False)


def write_fsm(path: Path, vertices_voxels: np.ndarray, faces: np.ndarray) -> None:
    v = np.ascontiguousarray(vertices_voxels, dtype="<f4")
    f = np.ascontiguousarray(faces, dtype="<u4")
    with path.open("wb") as fh:
        fh.write(_HEADER.pack(MAGIC, v.shape[0], f.shape[0]))
        fh.write(v.tobytes())
        fh.write(f.tobytes())


def read_fsm(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = Path(path).read_bytes()
    magic, nv, nf = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"{path}: not an FSM1 mesh")
    o = _HEADER.size
    v = np.frombuffer(data, dtype="<f4", count=nv * 3, offset=o).reshape(nv, 3)
    o += 12 * nv
    f = np.frombuffer(data, dtype="<u4", count=nf * 3, offset=o).reshape(nf, 3)
    return v.copy(), f.copy()


def fetch_meshes(bundle: Path, neuron_ids: np.ndarray, indices: np.ndarray, lod: int = 3,
                 overwrite: bool = False) -> dict:
    """Fetch and write the meshes of the given pack indices; returns the index document."""
    out = Path(bundle) / "meshes"
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    doc = json.loads(index_path.read_text()) if index_path.is_file() else {"lod": lod, "voxel_nm": VOXEL_NM, "neurons": {}}
    cv = None
    for i in np.unique(np.asarray(indices)).tolist():
        key = str(int(i))
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
                               "triangles": int(faces.shape[0]), "file": f"meshes/{i}.fsm"}
        print(f"  mesh {i:7d} bodyId {body:12d}  {verts.shape[0]:7,d} v {faces.shape[0]:8,d} t  "
              f"{time.perf_counter() - t:.1f}s", file=sys.stderr)
        index_path.write_text(json.dumps(doc, indent=1) + "\n")
    index_path.write_text(json.dumps(doc, indent=1) + "\n")
    return doc
