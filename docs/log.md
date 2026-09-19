# Log

Dated notes on what was built and measured. Newest last.

## 2026-09-18: phase 0, data and one brain

Machine: Apple M3 Pro, 36 GB, macOS 25.6. Python 3.12.13, mlx 0.32.2,
mlx-lif-engine at commit `02657cf` (2026-09-15).

- Fetched the three MaleCNS v1.0 tables (1.1 GB). Hashes in `data/sources.lock.json`.
- Compiled the engine's pack: 166,700 neurons, 24,469,412 signed edges,
  188.6 MiB, 93 s. Dataset tag `male-cns-v1.0-superclass-non-null-known-nt`.
  Signs: ACh +1, GABA and glutamate -1; other transmitters drop their outgoing edges.
- `Session` (stateful stepping over the engine's two Metal kernels) is
  bit-identical to `engine_fused.run` on 1,500 ticks with 50 hub neurons at
  150 Hz, split across three uneven steps: same per-neuron counts, same events.
- Smoke run, `fruitless smoke --seconds 1 --seed 0`: LB3b_R + LB3c_R (17
  neurons) at 100 Hz for one biological second, stepped in 125 ms segments.

  | measure | value |
  |---|---|
  | wall per biological second | 0.93 s |
  | total spikes | 35,150 |
  | neurons that fired | 1,919 |
  | sweet GRN rate | 102 Hz |
  | MN9_L | 60 Hz |
  | MN9_R | 0 Hz |
  | DNp01 | 0 Hz |

  The engine's README reports MN9_L 52.97 Hz and MN9_R 0.20 Hz for the same
  drive averaged over 30 trials, so one trial at 60 Hz is consistent.
- Activity bundle sizes for that second: whole-brain layer at 50 ms bins
  74 KB; hero layer (21 neurons) at 10 ms bins 6 KB. Linear extrapolation to a
  three minute take: about 13 MB per fly for the soma layer under this drive.
  The 200 MB per take budget in the plan has a lot of room; denser drives
  will cost more.
- Type name checks against the annotation table: `JO-A.*` and `JO-B.*` select
  138 neurons; `pC1.*`, `pIP10`, `vPR6`, `dPR1`, `TN1.*` select 203; the broad
  `.* MN` regex selects 398 and includes leg types, so wing motor neurons must
  be listed explicitly.

## 2026-09-19: phase 1, the stage skeleton

- `stage/` is a Vite + TypeScript + three.js page. It loads a take bundle,
  draws the 139,662 soma points that have a position (x right, body axis
  vertical so the brain sits above the ventral nerve cord, y as depth), and
  colors them from the 50 ms soma layer while a transport scrubs. Playback is
  a requestAnimationFrame clock at 0.1x to 1x until audio exists.
- `fruitless bundle takes/smoke` assembles `stage/public/takes/smoke/`:
  take.json, shared soma positions (float32 per pack index, NaN when none,
  2.0 MB), superclass codes (166 KB), the copied activity layers and the
  smoke report with its circuit groups.
- `fruitless meshes <bundle>` fetches hero neuron meshes from the release's
  precomputed multi-resolution Draco source over public HTTPS with
  cloud-volume (optional extra `meshes`). LOD 3 is the coarsest and enough:
  the 21 smoke neurons are 178k vertices and 5.5 MB in the FSM1 format
  (float32 positions in voxels, uint32 triangles). The two giant fibers are
  the largest at 64k and 58k vertices; MN9_L is 28k; a sweet GRN is about 1k.
  Fetch took 19 s for 21 neurons, most of it per-request latency.
- Verified in Chrome: the giant fibers run from the brain down the neck into
  the nerve cord as expected, MN9_L glows amber while the readout strip shows
  it at 60 to 70 Hz, the sweet GRNs glow, MN9_R and DNp01 stay dark. The plan's
  acceptance line named DNp01; under the sweet drive it is silent, so the
  pathway watched is sweet GRN to MN9, which is the one the engine validates.
- Readout rates are per 10 ms bin (one spike = 100 Hz), smoothed with a 0.1
  exponential moving average, and the loop walks every bin skipped by a slow
  frame so the first frame's shader compile stall does not drop spikes.
- Known visual debt: the optic lobes saturate to white because 89k points
  overlap; point size and opacity want a pass once there are several flies.
- CI on Linux: mlx installs but cannot load libmlx.so; engine-dependent tests
  now skip there with `importorskip(..., exc_type=ImportError)` and the
  workflow is green.
