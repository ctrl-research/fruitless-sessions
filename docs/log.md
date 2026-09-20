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

## 2026-09-19: what moves the legs? (phase 4 probe)

One biological second per condition, seed 0, rates averaged over each group.
Leg MN groups are the explicit leg motor types split by `subclass` (fl, ml,
hl) and side; about 60 to 68 neurons each. Wing MNs are the 56 wing types.

| drive | fl_L | fl_R | ml_L | ml_R | hl_L | hl_R | wing | fired |
|---|---|---|---|---|---|---|---|---|
| DNp09 100 Hz (forward walking DN) | 0.6 | 0.4 | 2.5 | 2.3 | 1.6 | 3.4 | 40 | 4,048 |
| DNa02 100 Hz (steering DN) | 1.7 | 0.7 | 2.3 | 1.4 | 1.9 | 3.6 | 40 | 4,356 |
| MDN 100 Hz (backward walking) | 1.6 | 0.9 | 4.3 | 3.1 | 3.5 | 5.0 | 42 | 3,951 |
| DNp09 200 Hz | 1.0 | 0.5 | 4.4 | 4.9 | 2.4 | 5.8 | 42 | 3,711 |
| DNg11, DNp20 100 Hz | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 |
| leg sensory, ProLN_L 100 Hz (331 afferents) | 3.2 | 1.2 | 1.2 | 1.2 | 1.2 | 1.2 | 10 | 4,008 |
| leg sensory, MesoLN_L 100 Hz | 3.9 | 2.4 | 8.0 | 4.1 | 3.9 | 3.5 | 41 | 12,045 |
| **excitatory premotor pool of fl_L, 60 Hz (60 neurons)** | **36.6** | 13.5 | 7.3 | 2.8 | 4.7 | 3.4 | 45 | 4,565 |
| same at 120 Hz | 55.9 | 14.9 | 8.5 | 2.8 | 5.9 | 2.9 | 47 | 4,990 |
| excitatory premotor pool of hl_R, 60 Hz | 0.4 | 1.9 | 0.6 | 2.4 | 5.8 | **41.1** | 0.7 | 751 |
| **tripod pools fl_L + ml_R + hl_L, 60 Hz** | **35.7** | 11.3 | 6.2 | **33.3** | **36.1** | 10.0 | 49 | 5,161 |

- Descending walking commands do not walk in this model. The strongest
  inputs to a leg's motor neurons are inhibitory premotor interneurons
  (IN19A, IN21A, IN13A, IN16B lineages, all negative), so a pure LIF with no
  central pattern generator or proprioceptive loop leaves leg MNs near
  silent. DNg11 and DNp20 have no signed outgoing edges at all (unclear
  transmitter) and do nothing.
- Every descending drive recruits wing MNs at about 40 Hz. Wings are the
  cheap motor output of this connectome.
- A leg's excitatory premotor pool, the top 60 positively weighted
  presynaptic partners of that leg's MNs excluding other MNs (types like
  IN03A, IN04B, IN20A.22A, IN21A012, ascending ANXXX006, a few DNge), fires
  that leg's MNs selectively at 37 Hz with 3 to 14 Hz elsewhere. Driving the
  tripod set fires the three tripod legs at 33 to 36 Hz against 6 to 11 Hz
  for the other three. That is the bass fly's drive.
- Consequence for honesty: the bass line's gait timing is the conductor's,
  because the connectome as modelled does not generate a gait. The fly
  contributes which motor neurons fire, how strongly, and the crosstalk
  between legs. The page will say exactly that.
- Left and right wing MN rates were symmetric under every drive, including
  unilateral DNa02. Drum voices will be split by muscle type (power vs
  steering), not by side.

## 2026-09-19: phase 4, the rhythm section

- Three flies on the same 72 s blues (sax, bass, drums), full brains each,
  coupled through their ears by the tune's coupling matrix. The head is played
  into every fly's ears in head sections; between steps each fly hears the
  others' motor intensity, split by register (sax high, drums middle, bass low).

  | measure | value |
  |---|---|
  | wall time | 330 s (4.6 s per biological second for three brains) |
  | total spikes | 18,259,630 |
  | notes | sax 132, bass 144, drums 258 |
  | activity layers | sax 19 MB, bass 24 MB, drums 9 MB |
  | hero meshes, 522 neurons, LOD 3 decimated to 35 % | 39 MB |
  | bundle | 93 MB |

- Bass (`fruitless.flies.bass`): the conductor drives the tripod premotor
  pools in alternation on the beat (60 Hz on the stepping tripod's pools for
  the first half of its beat, 4 Hz otherwise). Readout is six leg MN rates,
  two tripod step flags and mean load. A footfall onset is a note: left tripod
  root or fifth, right tripod third or seventh, approach tone into a chord
  change, velocity from the stepping legs' rate.
- Drums (`fruitless.flies.drums`): DNa02 at 70 Hz plus the ears. Power MN
  rate is kick and ride, steering MN rate is snare and hi-hat, hg is toms,
  burstiness is ghost notes, the giant fiber is a crash. Synthesised from
  noise and pitched thumps, deterministic.
- `fruitless remap` re-runs mappers and audio from a take's recorded motor
  readouts without simulating, so musical rules iterate in seconds instead of
  minutes. It found a bug straight away: chord tones were sorted from C, so
  the bass played C on an F7. Tones are now ordered from the root.
- Meshes: quadric decimation (pyfqmr, `--decimate 0.35`) in the fetch. 522
  neurons across three flies at 39 MB against 180 MB for 641 at float32 in
  phase 2. `mesh_groups` per fly chooses which groups are meshes; ears and
  premotor pools stay as points.
- Stage: one performer per fly, brain above riser, side by side; bass on an
  upright, drummer behind a kit whose pieces nudge on hits; rigs for bass
  (legs lift with their MN rate, foreleg plucks on a footfall) and drums (both
  wings beat with power MN rate, hind leg stamps the kick); panels follow the
  soloist; the camera frames the bandstand from the canvas aspect and pans
  toward the soloist until the user takes over.
- Verified in Chrome during playback: bass pose lifts legs 0.85/0.50/0.85
  left and 0.57/0.79/0.48 right (the tripod pattern), drummer flap 0.58 rad,
  sax pathway rates on the strip, all three nerve cords glowing.
- The plan's acceptance line asked for the bass fly's `JO-*` meshes to light
  when the sax plays; ears are soma points, not meshes, so that reads on the
  readout strip (jo_a 35 Hz, jo_b 48 Hz while the head plays) rather than on
  a mesh.
- Page feedback applied the same day: one shared circular platform with a
  brass rim and the band in an organic triangular formation (drums back
  centre, soloists forward left and right), a house spotlight from a ceiling
  lamp with a faint visible beam, a `brain activity` toggle (default on) that
  hides the points and meshes, a `stats` toggle (default off, remembered in
  localStorage) for the readout, motor, rig and meta panels, and a take
  dropdown fed by `stage/public/takes/index.json`, which `fruitless bundle`
  writes. Each entry shows how many runs of `take` and `remap` produced the
  result, counted in the take's `iterations` field.

## 2026-09-19: does the ring hold a bump? (phase 5 probe)

- EPG instances carry protocerebral bridge glomerulus labels, `EPG(PB08)_L1`
  .. `_L8` and `_R1` .. `_R8`, so each of the 46 EPGs has a ring angle:
  wedge k at (k - 0.5)/8 of a turn. PEN_a and PEN_b carry the same labels;
  Delta7 spans glomeruli (`Delta7(PB15)_L4R5_R`).
- The attractor's wiring is present: EPG to Delta7 is strongly excitatory
  (summed +19,896), Delta7 to EPG inhibitory (-4,294, ring-wide), and EPG to
  PEN to EPG is locally positive (effective diagonal 7,451 vs off-diagonal
  2,065).
- The dynamics are not. Driving one wedge's six EPGs at 60 Hz gives a clean
  bump (population vector magnitude 1.0 at the driven angle), but in the
  100 ms after the drive stops the ring is silent. There is no persistent
  activity in this LIF with these constants, so no memory of heading.
  PEN_a drive on one side alone (10 neurons at 40 Hz) yields 20 to 35 EPG
  spikes per 100 ms with a wandering vector (magnitude 0.1 to 0.5), not a
  rotation.
- Consequence: the piano fly's key is written into the ring by the conductor
  (the chord root as a driven EPG wedge, the way a visual landmark would set
  heading) and read back as the population vector. What the fly adds is the
  ring's own noise, inertia and crosstalk. In free style there is no chart, so
  the ring is pushed only by the ear imbalance through PEN_a left and right,
  and the key wanders. The page says so.

## 2026-09-19: phase 5, the pianist, the mushroom body and free style

- Piano fly (`fruitless.flies.piano`): EPG wedges from the protocerebral
  bridge labels, PEN_a left and right, PAM and PPL1 as drive groups; readout
  is the EPG population vector (angle and magnitude), EPG rate, MBON rate and
  an `mb_gain` (MBON rate over its running baseline, 0.5 to 1.5). Eight
  wedges map onto the circle of fifths; `key_from_bump` is the exact inverse
  of `wedge_for_pitch_class` (tested for all twelve keys).
- Comping (`PianoMapper`): rootless voicings on beats 2 and 4 and the "and"
  of 4, two-note shells when the bump is diffuse, four notes when sharp,
  velocity from EPG rate times `mb_gain`, silent when the ring is quiet.
- Mushroom body teaching signal: at each beat the soloist's most recent note
  is checked against the chord; a chord tone drives PAM at 50 Hz (reward), a
  note outside the scale drives PPL1 at 50 Hz (punishment). MBON output over
  baseline then scales the pianist's touch. No plasticity is modelled; this
  is a gain, and the page says so.
- Free style (`tunes/fruitless-session-1`, 24 bars at 132, no chart, no
  melody): the tune's key seeds bar 1; each bar line the piano's bump names
  the key as a dominant seventh, which everyone else plays on. The ring is
  held on its current key at 33 Hz (a chart gives 60) while the ear imbalance
  pushes PEN_a, so the key wanders. First run nobody but the drums played:
  uniform background drive gives a near-zero population vector, so no key was
  ever named. Seeding and holding fixed it.

  | take | wall | spikes | notes (sax / bass / drums / piano) | bundle |
  |---|---|---|---|---|
  | blues-in-f, four flies, 72 s | 448 s | 20.2 M | 132 / 144 / 258 / 282 | 118 MB |
  | fruitless-session-1, four flies, 44 s | 254 s | 12.1 M | 99 / 96 / 173 / 144 | 93 MB |

  Keys the ring named in the session, bar by bar: C7 C7 C7 F7 F7 Eb7 A7 B7 B7
  Gb7 C7 F7 Eb7 A7 A7 B7 Gb7 F7 Eb7 A7 A7 A7 A7 A7. It moves in fourths and
  fifths and settles late, which is what a wedge ring pushed by ear imbalance
  should do.
- Stage: a small upright piano, a piano rig (head yaw follows the bump, both
  forelegs drop on comps, abdomen swells with mushroom body gain), the caption
  shows the key the ring named in free style, one score lane per member, and
  seating with the sax on the outer side of the bassist.
- Mesh budget is now the concern: four flies are 765 hero neurons and 57 MB
  even after decimation; the blues bundle is 118 MB. Sharing meshes between
  bundles or dropping the ear groups from the hero layers is the next lever.

## 2026-09-19: phase 6, publishing

- Shared assets. Soma positions and superclass codes moved to
  `stage/public/takes/shared/` and hero meshes to a single store at
  `stage/public/takes/meshes/` with a `store.json`; each bundle keeps its own
  `meshes.json` listing the subset it draws and points at the store with
  `../meshes/<idx>.fsm`. The store prunes neurons no bundle references. The
  takes root went from 221 MB to 156 MB with three takes; a second four-fly
  take now costs 37 MB (activity layers and audio) instead of 93.
- `scripts/publish` builds the stage under the `/fruitless-sessions/` base
  path and force-pushes one orphan commit to `gh-pages`, so the branch never
  grows. `.github/workflows/pages.yml` deploys that branch. Publishing is a
  local step because the build needs the takes and those need Metal.
- Reproducibility: every take records `counts_sha256`, a digest of each fly's
  per-neuron spike counts. Same seed, tune, pack and engine give the same
  digest; earlier phases already showed identical spike totals across reruns.
- README has the stage screenshot, the publish and reproduce sections and the
  honest scope paragraph. Not yet done: the actual first publish (the repo is
  private; GitHub Pages on a private repository needs a paid plan, and the
  alternative is the homelab cluster), and the `awesome-fly` submission.

## 2026-09-19: Take Five, and meters other than 4/4

- Tune files take a `meter` (`5/4`); the beat is a quarter. Chart rows carry
  one entry per beat, the melody is in beats, and swing eighths still work.
  Drums accent 3 + 2 in five (kick on 1 and 4, snare on 3 and 5, ride every
  beat); the piano comps on 2 and 4 with the anticipation on the last beat.
- Chord roots accept jazz flat spelling (`Ebm7`, `Bb7`); music21 wants `E-m7`.
- `tunes/take-five` has the changes of "Take Five" (Desmond, 1959): the
  Ebm7 / Bbm7 vamp with the bridge, AABA, 32 bars at 176, form head, sax
  chorus, head, 164 s of biological time for four flies. The shipped
  `head.abc` is an original 5/4 line over those changes, not the melody;
  drop a lead sheet in as ABC or MIDI and re-run `fruitless take` and the sax
  plays that instead.

## 2026-09-19: arrangement mode, and the flies learn a MIDI

- A tune can point at a MIDI arrangement instead of a chart and melody
  (`arrangement:`, `parts:` mapping roles to track names, `lead:`). Tempo,
  meter and bar count come from the file; the form is read off the lead
  part (bars where it plays are `head`, the rest `vamp`); the chart is
  estimated per half-bar by template match against every m7, maj7 and 7 at
  every root, with the bass root weighted. The estimate caught a half-step
  modulation into E minor for the head out that a fixed vocabulary had
  misread as B major and Bb7.
- Written-part mappers: the part decides pitch and timing, the fly decides
  whether the note sounds and how hard. Bass notes need mean leg MN rate
  above 6 Hz; drum hits are gated by the muscle group that would play them
  (kick, ride and crash by power MNs, snare and hats by steering MNs, toms by
  hg); piano chords need EPG rate above 1 Hz and thin to their outer voices
  when the bump is diffuse, velocity from EPG rate times mushroom body gain.
  The sax follows the lead part as it already followed a melody.
- The arrangement file itself stays out of the repo (`tunes/**/*.mid` is
  ignored): it is the user's copy of a published arrangement.
- Grid steps are now rounded to 0.1 ms ticks, not milliseconds; at 178 BPM
  the old rounding would have drifted the music against the brains by about
  0.6 s over the take.

- Dropped the run count from the take dropdown. It counted how many times
  `take` or `remap` had been run while building and read as if the flies had
  trained. Nothing here trains: a take is one deterministic pass. The
  `iterations` field stays in `take.json` as plain bookkeeping.

## 2026-09-19: first publish

- Live at https://fruitless-sessions.j6n.dev/ (GitHub Pages, workflow
  deploy, custom domain), 355 MB with four takes: the blues, the free-style
  session, Take Five from the supplied arrangement, and the phase 0 smoke.
- Three things bit on the way. A push-triggered workflow only runs if the
  pushed branch contains it, so the publish script now copies `pages.yml`
  into the orphan commit. The second publish failed silently because the
  local `gh-pages` branch from the first run still existed; the script now
  builds on a throwaway orphan branch and pushes it to `gh-pages` by ref.
  And the `github-pages` environment only allowed the default branch to
  deploy; the environment's branch policy now lists `gh-pages` and `main`.

## 2026-09-19: strict written parts, and exact times

- Jonathan heard notes missing from the Take Five head. Two causes. Gating:
  a written note only sounded if the fly's circuit was active at that grid
  step, which dropped 75 of the sax's 328 notes and a thousand drum hits.
  Sampling: the sax read the melody once per grid step, so at 178 BPM any
  note shorter than a swing eighth, or two notes inside one step, merged.
- Tunes now take `written: strict | gated`. Strict sounds every written note
  and leaves the fly only velocity and articulation; gated is the old
  behaviour. Take Five is strict. In arrangement mode every role plays its
  written notes at their exact written times, not quantised to the grid, and
  piano notes that start together are one chord.
- Four commits with the publish fixes had landed on the feature branch after
  PR #9 merged; they are cherry-picked here.

## 2026-09-20: Fly Me to the Moon, from a big band chart

- A second arrangement, fifteen tracks all named alike: two drum tracks,
  piano, nylon guitar comping, jazz guitar, bass, flute, baritone and two
  alto saxes, two trombones, trumpet, muted trumpet and a brass pad. 116 BPM
  in 4/4 after a 1.2 s count-in at another tempo; 73 bars.
- Arrangement loader additions: parts may name tracks as `track:N` or
  `program:N` as well as by name; `skyline: [role]` reduces several tracks to
  one line by keeping the highest sounding note (a soloist reading a section
  part); the dominant tempo, the one holding for most of the file, sets the
  grid and its start; rests of one or two bars inside the lead's line stay in
  the head rather than splitting the form.
- Quartet reduction: sax takes the skyline of jazz guitar, lead alto and lead
  trumpet; piano takes the nylon guitar comping and the piano hits; bass and
  both drum tracks map directly. Trombones, baritone, flute, muted trumpet and
  the brass pad are not played. The chart estimate reads as the tune in C.
- This is the default take on the site.
