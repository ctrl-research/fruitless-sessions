# Fruitless Sessions

Simulated fruit fly nervous systems, built from the Janelia FlyEM
[male CNS v1.0](https://male-cns.janelia.org/) connectome, playing together as a
jazz ensemble. The product is a static web page that plays a recorded set and,
in sync with the music, shows each fly's brain activity on its real neuron
anatomy next to a 3D animated fly playing its instrument.

Status: **phase 1**. Data pipeline, connectome pack, a stateful simulation
session, the activity bundle format, and a stage page that scrubs a take's
whole-brain activity and hero neuron meshes. No music and no bodies yet.
See [`docs/plan.md`](docs/plan.md) for the plan and
[`docs/reference.md`](docs/reference.md) for the data facts it relies on.

## What this is, honestly

Every fly is the Shiu et al. 2024 leaky integrate-and-fire model run on the
166,700 neurons and 24.5 million signed connections of the MaleCNS release,
through Kisame76's [MLX engine](https://github.com/Kisame76/mlx-lif-engine).
The connectome gives wiring, synapse counts and predicted transmitter. It does
not give synaptic weights, time constants, neuromodulation or plasticity. One
global weight per synapse, fitted to the FlyWire female brain, is reused here
unchanged. Rhythm and harmony come from a conductor and from small, documented
readout functions, not from the neurons. It is a model of the wiring, not a fly.

## Setup

Apple silicon only (the engine is Metal). Tool versions are pinned in
`.tool-versions`; install them with `mise install`.

```bash
uv sync --extra dev
uv run fruitless fetch-data      # ~1.1 GB, three Feather tables, SHA-256 checked
uv run fruitless pack            # ~90 s, writes data/pack/male_cns_v1 (189 MiB)
uv run pytest                    # unit tests plus one GPU parity test
uv run fruitless smoke           # sweet taste drives MN9 for 1 s; writes takes/smoke/
uv run fruitless bundle takes/smoke                    # -> stage/public/takes/smoke
uv sync --extra meshes && uv run fruitless meshes stage/public/takes/smoke   # hero meshes
cd stage && npm install && npm run dev                 # http://localhost:5173/?take=smoke
```

`fruitless select 'JO-A.*' 'JO-B.*'` lists the neurons a type regex selects.

## Layout

```
src/fruitless/
  data/        release tables: lock file, fetch, annotations
  flies/       neuron selection by MaleCNS annotation; shared circuits
  sim/         Session: the engine's kernels, advanced one grid step at a time
  recording/   binned activity, hero meshes and take bundles the stage reads
  cli.py
stage/         the web page: Vite + TypeScript + three.js
data/sources.lock.json   what bytes the tables are; copied into every take
docs/                    plan, reference, log
tests/
```

## Data and credit

MaleCNS v1.0 is CC BY 4.0: FlyEM at HHMI Janelia, the University of Cambridge,
the MRC Laboratory of Molecular Biology, Google Research and the MaleCNS
collaboration. Berg, Beckett, Costa, Schlegel et al., *Sexual dimorphism in the
complete Drosophila male central nervous system connectome*, Cell 2026.
Nothing from the release is redistributed in this repository.

The simulation engine is Kisame76's `mlx-lif-engine` (MIT). The model is Shiu
et al., *A Drosophila computational brain model reveals sensorimotor
processing*, Nature 2024.
