"""`fruitless` command line: data, pack, and phase-0 checks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from fruitless import paths


def cmd_fetch_data(_args) -> int:
    from fruitless.data.sources import fetch_all
    got = fetch_all()
    for k, p in got.items():
        print(f"ok  {k:18s} {p}")
    return 0


def cmd_pack(args) -> int:
    from lif import compile_pack_malecns

    from fruitless.data.sources import load_lock, verify
    lock = load_lock()
    for s in lock.values():
        if not verify(s, hash_check=False):
            print(f"missing or wrong size: {s.path()}; run `fruitless fetch-data`", file=sys.stderr)
            return 2
    argv = [
        "--annotations", str(lock["annotations"].path()),
        "--neurotransmitters", str(lock["neurotransmitters"].path()),
        "--connectivity", str(lock["connectivity"].path()),
        "--out", str(args.out),
    ]
    sys.argv = ["lif.compile_pack_malecns", *argv]
    return compile_pack_malecns.main()


def cmd_select(args) -> int:
    from lif import core

    from fruitless.flies.select import Resolver, Selection
    pack = core.load_pack(args.pack, verify_hashes=False)
    r = Resolver(pack.neuron_ids)
    idx = r.indices(Selection("cli", types=tuple(args.type_regex)))
    types = r.types_of(idx)
    inst = r.instances_of(idx)
    from collections import Counter
    print(f"{idx.size} neurons")
    for t, n in sorted(Counter(types).items(), key=lambda kv: str(kv[0])):
        print(f"  {n:6d}  {t}")
    if args.verbose:
        for i, t, ins in zip(idx.tolist(), types, inst, strict=True):
            print(f"  idx {i:7d}  bodyId {int(pack.neuron_ids[i])}  {ins or t}")
    return 0


def cmd_smoke(args) -> int:
    """Phase 0 check: sweet taste (LB3b_R + LB3c_R at 100 Hz) drives MN9, as the
    engine's own MaleCNS film does. Writes a whole-brain activity layer in bundle
    format so the stage has something to load in phase 1."""
    from lif import core

    from fruitless.flies.select import Resolver, Selection
    from fruitless.recording.activity import ActivityWriter
    from fruitless.sim.session import Session, constant_drive

    t_load = time.perf_counter()
    pack = core.load_pack(args.pack)
    r = Resolver(pack.neuron_ids)
    sweet = r.indices(Selection("sweet", instances=("LB3b_R", "LB3c_R")))
    mn9 = r.resolve({"MN9_L": Selection("l", instances=("MN9_L",)),
                     "MN9_R": Selection("r", instances=("MN9_R",))})
    gf = r.indices(Selection("gf", types=("DNp01",)))
    print(f"pack loaded in {time.perf_counter() - t_load:.1f}s; "
          f"{sweet.size} sweet GRNs, MN9_L={mn9['MN9_L'].tolist()}, MN9_R={mn9['MN9_R'].tolist()}, "
          f"DNp01={gf.tolist()}")

    rng = np.random.default_rng(args.seed)
    session = Session(pack, sweet, edge_split=1)
    out = Path(args.out)
    writer = ActivityWriter(out / "soma", bin_ms=args.bin_ms, chunk_s=args.chunk_s,
                            n_neurons_pack=pack.n_neurons)
    hero_idx = np.unique(np.concatenate([sweet, mn9["MN9_L"], mn9["MN9_R"], gf]))
    hero = ActivityWriter(out / "hero", bin_ms=10, chunk_s=args.chunk_s,
                          n_neurons_pack=pack.n_neurons, subset=hero_idx)

    n_ticks = int(args.seconds * 1000 * 10)
    step_ticks = 1250   # 125 ms, one swing eighth at 120 BPM
    t0 = time.perf_counter()
    total = 0
    done = 0
    while done < n_ticks:
        k = min(step_ticks, n_ticks - done)
        draws = constant_drive(session, sweet, args.rate_hz, k, rng)
        res = session.step(draws)
        writer.add(res.events, k)
        hero.add(res.events, k)
        total += int(res.counts.sum())
        done += k
    wall = time.perf_counter() - t0
    counts = session.total_counts()
    meta = writer.close()
    hmeta = hero.close()

    def hz(idx):
        return float(counts[idx].sum()) / max(idx.size, 1) / args.seconds

    report = {
        "seconds_bio": args.seconds,
        "seconds_wall": round(wall, 2),
        "wall_per_bio_second": round(wall / args.seconds, 3),
        "total_spikes": total,
        "neurons_fired": int((counts > 0).sum()),
        "sweet_grn_hz": round(hz(sweet), 2),
        "MN9_L_hz": round(hz(mn9["MN9_L"]), 2),
        "MN9_R_hz": round(hz(mn9["MN9_R"]), 2),
        "DNp01_hz": round(hz(gf), 2),
        "soma_layer": meta,
        "hero_layer": hmeta,
        "pack_dataset": pack.manifest.get("dataset"),
        "seed": args.seed,
        "circuit": {"sweet_grn": sweet.tolist(), "MN9_L": mn9["MN9_L"].tolist(),
                    "MN9_R": mn9["MN9_R"].tolist(), "DNp01": gf.tolist()},
    }
    (out / "smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


def cmd_bundle(args) -> int:
    """Assemble a take bundle for the stage from a take directory (takes/<name>)."""
    from lif import core

    from fruitless.recording.bundle import default_stage_dir, flies_from_take_dir, write_bundle
    pack = core.load_pack(args.pack, verify_hashes=False)
    take = Path(args.take)
    flies, extra, audio = flies_from_take_dir(take)
    rep = json.loads((take / ("take.json" if (take / "take.json").is_file() else "smoke.json")).read_text())
    out = Path(args.out) if args.out else default_stage_dir() / args.name
    m = write_bundle(out, args.name, pack, flies, duration_s=rep.get("seconds_bio", 0.0),
                     seed=rep.get("seed"), extra=extra, audio_src=(take / audio) if audio else None)
    print(f"bundle: {out}  flies={[f['role'] for f in m['flies']]}  duration={m['duration_s']}s  "
          f"audio={m['audio']}  soma={m['shared']['with_soma']}/{m['shared']['n_neurons']}")
    from fruitless.recording.bundle import write_index
    idx = write_index(out.parent)
    print(f"index: {out.parent / 'index.json'} ({len(idx)} takes)")
    return 0


def cmd_take(args) -> int:
    """Run a studio take of a tune: simulate, record, map to notes, render audio."""
    from fruitless.conductor.take import run_take
    out = Path(args.out) if args.out else paths.TAKES / Path(args.tune).parent.name
    rep = run_take(Path(args.tune), out, seed=args.seed, pack_dir=args.pack,
                   render_audio=not args.no_audio)
    print(json.dumps({k: rep[k] for k in ("seed", "seconds_bio", "seconds_wall", "total_spikes", "audio")}, indent=2))
    for f in rep["flies"]:
        print(f"  {f['role']}: {f['n_notes']} notes")
    print(f"take: {out}")
    return 0


def cmd_remap(args) -> int:
    """Re-run mapping and audio from a take's recorded readouts, without simulating."""
    from fruitless.conductor.take import remap
    rep = remap(Path(args.take), args.tune, render_audio=not args.no_audio)
    for f in rep["flies"]:
        print(f"  {f['role']}: {f['n_notes']} notes")
    print(f"audio: {rep['audio']}")
    return 0


def cmd_meshes(args) -> int:
    """Fetch hero meshes for a bundle: every neuron in its flies' circuit groups."""
    from lif import core

    from fruitless.recording.meshes import fetch_meshes
    pack = core.load_pack(args.pack, verify_hashes=False)
    bundle = Path(args.bundle)
    manifest = json.loads((bundle / "take.json").read_text())
    idx = sorted({i for f in manifest["flies"]
                  for g, members in f["circuit"].items()
                  if not f.get("mesh_groups") or g in f["mesh_groups"]
                  for i in members})
    if args.indices:
        idx = sorted(set(idx) | set(args.indices))
    print(f"{len(idx)} hero neurons -> {bundle.parent / 'meshes'} (shared store, lod {args.lod})", file=sys.stderr)
    doc = fetch_meshes(bundle, pack.neuron_ids, np.array(idx, dtype=np.int64), lod=args.lod,
                       overwrite=args.overwrite, decimate_ratio=args.decimate)
    manifest["meshes"] = {"index": "meshes.json", "lod": args.lod, "decimate": args.decimate,
                          "n": len(doc["neurons"]),
                          "vertices": sum(m["vertices"] for m in doc["neurons"].values()),
                          "bytes": sum(m.get("bytes", 0) for m in doc["neurons"].values())}
    (bundle / "take.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["meshes"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fruitless", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch-data", help="download and verify the MaleCNS v1.0 tables").set_defaults(fn=cmd_fetch_data)

    p = sub.add_parser("pack", help="compile the tables into the engine's pack")
    p.add_argument("--out", type=Path, default=paths.PACK)
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("select", help="list neurons whose type matches regexes")
    p.add_argument("type_regex", nargs="+")
    p.add_argument("--pack", type=Path, default=paths.PACK)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_select)

    p = sub.add_parser("smoke", help="phase-0 check: sweet taste drives MN9; writes an activity layer")
    p.add_argument("--pack", type=Path, default=paths.PACK)
    p.add_argument("--out", type=Path, default=paths.TAKES / "smoke")
    p.add_argument("--seconds", type=float, default=1.0)
    p.add_argument("--rate-hz", type=float, default=100.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--bin-ms", type=int, default=50)
    p.add_argument("--chunk-s", type=float, default=10.0)
    p.set_defaults(fn=cmd_smoke)

    p = sub.add_parser("bundle", help="assemble a take bundle for the stage from a take directory")
    p.add_argument("take", type=Path, help="e.g. takes/smoke")
    p.add_argument("--name", default=None)
    p.add_argument("--role", default="smoke")
    p.add_argument("--pack", type=Path, default=paths.PACK)
    p.add_argument("--out", type=Path, default=None, help="default stage/public/takes/<name>")
    p.set_defaults(fn=cmd_bundle)

    p = sub.add_parser("take", help="run a studio take of a tune (simulate, record, notes, audio)")
    p.add_argument("tune", type=Path, help="e.g. tunes/blues-in-f/tune.yaml")
    p.add_argument("--out", type=Path, default=None, help="default takes/<tune dir name>")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--pack", type=Path, default=paths.PACK)
    p.add_argument("--no-audio", action="store_true")
    p.set_defaults(fn=cmd_take)

    p = sub.add_parser("remap", help="re-run mappers and audio from a take's motor readouts (no simulation)")
    p.add_argument("take", type=Path, help="e.g. takes/blues-in-f")
    p.add_argument("--tune", type=Path, default=None)
    p.add_argument("--no-audio", action="store_true")
    p.set_defaults(fn=cmd_remap)

    p = sub.add_parser("meshes", help="fetch hero neuron meshes into a bundle (needs --extra meshes)")
    p.add_argument("bundle", type=Path, help="e.g. stage/public/takes/smoke")
    p.add_argument("--pack", type=Path, default=paths.PACK)
    p.add_argument("--lod", type=int, default=3, help="3 is coarsest (~28k vertices for a big MN)")
    p.add_argument("--indices", type=int, nargs="*", default=None, help="extra pack indices")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--decimate", type=float, default=0.35, help="target triangle ratio after LOD 3 (1 = none)")
    p.set_defaults(fn=cmd_meshes)

    args = ap.parse_args(argv)
    if getattr(args, "cmd", None) == "bundle" and args.name is None:
        args.name = Path(args.take).name
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
