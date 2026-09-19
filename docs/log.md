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

## 2026-09-19: does the song pathway work in the model?

Before building the sax fly, one biological second per condition, seed 0,
Poisson drive on the named group, rates in Hz averaged over each group
(counts from `Session`, 125 ms steps):

| driven group (rate) | pC1_* | pC1x | pIP10 | vPR6 | dPR1 | TN1* | wing MNs | DNp01 | neurons fired |
|---|---|---|---|---|---|---|---|---|---|
| pC1_* (50 Hz, 148 neurons) | 58 | 88 | 82 | 0 | 51 | 19 | 30 | 0 | 4,435 |
| pC1_* (150 Hz) | 167 | 131 | 164 | 0 | 157 | 53 | 61 | 0 | 11,637 |
| pIP10 (100 Hz, 2 neurons) | 1 | 5 | 99 | 0 | 71 | 27 | 57 | 0 | 4,008 |
| JO-A*/JO-B* (100 Hz, 138 neurons) | 0 | 0 | 1 | 0 | 3 | 0 | 38 | 17 | 3,122 |

Wing MNs here are the 56 neurons of the explicit wing motor types (`DLMn *`,
`DVMn *`, `b1..b3 MN`, `hg1..4 MN`, `i1/i2 MN`, `iii1/iii3 MN`, `ps1/ps2 MN`,
`tp1/tp2 MN`, `tpn MN`).

- The published courtship chain is intact in the wiring: pC1 drives pIP10,
  pIP10 drives dPR1 and TN1, and wing motor neurons follow, with the response
  scaling with drive. That is the sax fly's readout path.
- `vPR6` never fires under any of these drives; it is likely gated by
  inhibition the model does not release. Leave it in the hero layer, do not
  read from it.
- pC1 drive does not recruit the giant fiber. Auditory drive does: 100 Hz on
  the Johnston's organ afferents fires `DNp01` at 17 Hz and the wing MNs at
  38 Hz, which is the startle you would expect from a loud sound. Two
  consequences for the design: flies will startle when the band gets loud
  (the trading-fours hand-off comes for free), and coupling gains need to be
  low enough that a fly does not startle continuously.
- Wall time per biological second rose with activity, 1.0 to 2.2 s, so a
  loud take costs more than a quiet one.

## 2026-09-19: phase 2, the sax plays the head

- `fruitless take tunes/blues-in-f/tune.yaml` runs a full studio take: one
  fly (sax), a 12-bar blues in F at 120 BPM, swing eighths, form head, one
  sax chorus, head out. 36 bars, 288 grid steps of 125 ms, 72 s of biological
  time. The head is an original riff written for the project, in ABC.

  | measure | value |
  |---|---|
  | wall time | 118 s (1.6 s per biological second under this drive) |
  | total spikes | 6,833,707 |
  | notes | 132 (93 before solo notes were made to start every beat) |
  | soma layer, 50 ms bins | 15 MB |
  | hero layer, 10 ms bins, 641 neurons | 4 MB |
  | audio, Opus in WebM | 1 MB |
  | hero meshes, 139 neurons, FSM2 | 41 MB |

  Two runs with the same seed gave identical spike totals: takes are
  deterministic from seed, tune and pack.
- Drive: pC1 at 60 Hz while a melody note sounds, 8 Hz on rests, 45 Hz
  steady in the solo. The head is also played into the ears: JO-A at up to
  60 Hz for high notes, JO-B for low ones. On the page `jo_a` reads 58 Hz on
  an F5 and `jo_b` 21 Hz on a C5, so the tonotopy split is visible.
- Readout (`fruitless.flies.sax`): song_on from TN1 rate, intensity from wing
  MN population rate, pulse from the coefficient of variation of wing MN
  spikes across 10 ms bins, pIP10 rate for the page. Mapper rules are in the
  docstring of `fruitless.conductor.mapper` and covered by tests.
- Audio: a small deterministic additive synth (`fruitless.render.synth`)
  renders the notes; ffmpeg encodes Opus (this ffmpeg has no Vorbis). The
  MIDI file is written too. `tinysoundfont` has an offline `generate` and
  would take a SoundFont later.
- Stage: the `<audio>` element is the clock once a take has audio (a detached
  `new Audio()` never started loading in Chrome; an element in the document
  does). Score strip shows sections, bar lines, note marks by pitch and the
  playhead; a caption shows bar, chord, section and the sounding note; a
  panel shows the motor readouts for the current step. Point updates now
  touch only neurons with heat, not all 166,700 per frame.
- Meshes: 641 circuit neurons at float32 were 180 MB, far over budget. Two
  changes: each fly names `mesh_groups` (sax: pIP10, vPR6, dPR1, TN1, wing
  MNs, giant fiber, GFC; pC1 and the ears stay as points), and the FSM2
  format quantizes positions to 16 bits inside each neuron's bounding box with
  uint16 indices where possible. 139 neurons are now 41 MB. Quadric decimation
  (pyfqmr) halves triangle counts again and is the next lever when more flies
  arrive; not wired in yet.
- Whole bundle for this take: 63 MB. Verified in Chrome: audio and transport
  agree to a few milliseconds, the pC1 to pIP10 to dPR1 to TN1 to wing MN
  chain reads live on the strip, and the wing MN meshes glow in the nerve cord
  while the head plays.

## 2026-09-19: phase 3, bodies

- The fly is procedural: `stage/src/body/fly.ts` builds it from capsules,
  spheres, cylinders and two bezier wing blades, with a Group at every joint
  (six legs of coxa, femur, tibia, tarsus; two wing hinges; head, antennae,
  proboscis, abdomen). No model file, no keyframes, no Blender.
- `stage/src/body/rig.ts` turns the take's motor readouts, the smoothed hero
  group rates and the sounding notes into a Pose every frame. The rules are
  data on the rig and the page prints them in a panel. Sax rules: right wing
  extends ~75° while `song_on` (the one-wing courtship song), vibration
  amplitude from wing MN rate, faster and jerkier on pulse song, body pitch
  from intensity, forelegs press the keys on note onsets, proboscis on the
  mouthpiece while a note sounds, antennae twitch with JO afferent rate, and a
  startle hop with both wings out when the giant fiber fires.
- `stage/src/body/instruments.ts` has a saxophone (tube along a spline, cone
  bell, keys, stand) and a riser. The performer stands to the left of its
  brain at a body length of about a fifth of the brain's radius.
- Verified in Chrome by reading the pose off the debug handle while the take
  plays: right wing 1.30 rad, left 0.12, flap 0.13 rad at 13 Hz, pitch
  0.08 rad, proboscis 1.0, forelegs raised, all following the readouts.
- Two page fixes fell out. The transport used to be created only after the
  41 MB of meshes had loaded, so an early click did nothing; meshes now load
  behind the transport. And when the browser refuses audio autoplay (which it
  does for synthetic clicks), the page now says so and runs on the frame clock
  instead of freezing at zero.
- Debt: the body is a stylised approximation and its proportions want an
  artist's pass; only the sax has a rig, the other roles use the idle rig.
