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
