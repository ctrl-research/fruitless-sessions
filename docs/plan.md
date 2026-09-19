# Fruitless Sessions: project plan

Simulated fruit fly nervous systems, built from the Janelia FlyEM **male CNS v1.0**
connectome, playing together as a jazz ensemble.

**The product is a web page.** It plays a recorded set and, in sync with the
music, shows each fly's brain activity on its real neuron anatomy next to a
3D animated fly playing its instrument. The **studio take** that produces the
recording, the spike data and the motor signals is a component that feeds the
page. Nothing runs live or on demand: simulations and recordings happen
offline, and the page only plays back what they produced.

Companion file: [`reference.md`](reference.md) holds the verified data schema,
cell type names, simulation parameters and tooling facts this plan relies on.

---

## 1. Concept in one paragraph

Each band member is a separate simulation of the same male brain with a
different circuit unmasked: auditory input through Johnston's organ, a role
circuit (courtship song, walking, flight, central complex, mushroom body), and
the motor output that circuit drives. Flies hear each other: one fly's motor
output is rendered to sound, and that sound is encoded as spike trains into the
others' auditory neurons. A conductor holds the clock, the chord chart and the
melody. For **familiar tunes** the soloist plays the head in and out and the
band solos over the form. For **free-style tunes** there is no chart and only
the flies' own coupling shapes the set. The same motor neuron activity that
becomes a note also moves the animated fly's legs, wings and body on stage, so
what you see the fly do, what you hear, and what lights up in its brain are one
signal seen three ways.

## 2. What we are honest about

- The connectome gives wiring, synapse counts and predicted transmitter. It
  does not give synaptic weights, time constants, neuromodulation or
  plasticity. The Shiu 2024 leaky integrate-and-fire model with one global
  weight is the community standard and is what we use. It is a model of the
  wiring, not a fly.
- A raw LIF network has no sense of tempo. Rhythm comes from the conductor's
  grid and from the readout mapping, not from the neurons. The page says so,
  and the readouts are small, documented and visible on the page itself.
- Every fly is the same male brain. Sexual dimorphism enters only through the
  female FlyWire brain used as the singer in a later phase.

## 3. The ensemble

| Role | Circuit (MaleCNS `type` names) | Motor readout | Instrument | Body animation driven by the same readout |
|---|---|---|---|---|
| Drums | Wing motor neurons `DLMn *`, `DVMn *`, `b1 MN`..`tp2 MN`; steering DN `DNa02` | Power, steering and hg MN rates, burstiness | Kit: power = kick and ride, steering = snare and hi-hat, hg = toms, giant fiber = crash | Wings beat the kit; hind leg stamps the pedal |
| Bass | Leg MNs (`Ti flexor MN`, `Tr extensor MN`, ...) by `subclass` fl/ml/hl, driven through each leg's connectome-derived excitatory premotor pool (walking DNs shown, not effective in the model) | Six leg-group rates, tripod step flags | Bass, footfall = note | Legs walk the bass line; forelegs pluck on footfall |
| Sax (soloist) | `pC1_*` cluster, `pIP10`, `vPR6`, `dPR1`, `TN1a_*`/`TN1c_*`, wing MNs | Pulse vs sine song, intensity | Lead voice | One wing extended and vibrating, as in real courtship song; body pitch with intensity |
| Piano (comping) | Central complex `EPG`, `PEN_a(PEN1)`, `PEN_b(PEN2)`, `Delta7`; mushroom body `KC*`, `MBON*`, `PAM*`, `PPL1*` | Bump angle and magnitude (8 wedges onto the circle of fifths), EPG rate, MBON gain | Rootless voicings on 2 and 4 | Head turns with the bump heading; forelegs drop on the keys; abdomen swells with reward |
| Ears (all) | `JO-A*`, `JO-B*`, `AMMC*` | input only | none | Antennae twitch with input rate |
| Learning (all) | `KC*`, `MBON*`, `PAM*`, `PPL1*` | reward and punishment | modulates readout gain | none |
| Singer (stretch) | FlyWire female v783: JO, `pC1*`, `vpoDN` | accept / reject | resolves or refuses the tune | Approaches or walks away |

Escape (`DNp01` giant fiber and `GFC1..4`) stays active in every fly. When it
fires, that fly drops out for a bar and its body does a startle jump. This is
the hand-off for trading fours and it is a real circuit doing a real thing.

## 4. The stage: the web page

A fully static site, built with Vite, TypeScript and three.js, hosted on
GitHub Pages or the homelab cluster. No backend, no simulation in the browser,
no live data. It loads a pre-rendered **take bundle** and plays it back.

**Layout.** A stage with the band arranged as on a bandstand, one 3D fly per
role, each with its instrument. Above or behind each fly, its brain: the whole
brain as 166,700 soma points, and the role circuit as real meshes, both
colored by activity. A transport bar at the bottom with the waveform, the form
(head, solos, trades, head out) marked, and the chart scrolling by. The user
can scrub, loop a section, and change playback speed.

**Sync.** The audio element is the clock. Every frame reads `currentTime` and
looks up the activity bin, the motor readouts and the MIDI events for that
moment. Nothing else keeps time.

**Brain layers per fly**, toggleable:
1. Soma points, all neurons, colored by binned activity (50 ms bins for this
   layer to keep the bundle small).
2. Role circuit meshes at full 10 ms resolution, colored by activity, always
   drawn on top.
3. Neuropil ROI shells with aggregate rate as a heat tint.
4. The readout: the handful of motor neurons that actually produce the notes,
   with a thread drawn from each to the instrument when they fire.

**Highlighting.** During a solo the camera moves to that fly and its brain
grows; the rhythm section shrinks but keeps playing. Clicking a neuron shows
its type, side, transmitter and what it is connected to in this take. Hovering
a MIDI note in the transport shows which neurons fired to make it.

**Body animation.** Each fly is a rigged glTF model with joints for six legs
(three segments each), two wings, head, antennae, proboscis and abdomen. The
rig is driven procedurally from the motor readouts every frame, not from
keyframes: leg MN rates per leg become joint angles through a documented gait
mapping, wing MN rates become wingbeat amplitude and asymmetry, JO input rate
twitches the antennae, the giant fiber triggers the startle. Instruments are
static props positioned so the driven limbs land on them. The mapping from
readout to joint is a small function per role and is shown on the page.

**Take bundle format** (what the studio produces and the page consumes):

```
takes/<name>/
  take.json          manifest: tune, seed, sign convention, coupling, engine version
  mix.ogg            rendered audio (the clock)
  <role>.mid         MIDI per instrument
  <role>/soma/       activity layer: activity.json + chunk_NNNN.bin, 50 ms bins, 10 s chunks;
                     per bin a sorted list of (uint32 model index, uint8 count) for neurons that fired
  <role>/hero/       same format at 10 ms bins over the role circuit only (subset.npy maps indices)
  <role>/motor.bin   float32 readouts per 10 ms (leg groups, wing groups, song class, bump heading)
  <role>/roi.bin     float32 per ROI per 50 ms
shared/
  soma-xyz.bin       166,700 soma positions, once
  hero-meshes/       glTF meshes per role circuit, once
  fly.glb            rigged body, once
```

**Data budget.** Target under 200 MB per three minute take, streamed in 10 s
chunks so playback starts fast. Whole-brain spikes are sparse and most neurons
are silent in a LIF connectome model, so an event list at 50 ms bins should fit.
If it does not, the soma layer drops to 100 ms bins before anything else is cut.

## 5. Architecture

```
                    +------------------+
                    |    conductor     |   clock, chord chart, melody,
                    |                  |   set form, coupling matrix
                    +--------+---------+
                             | ZeroMQ pub/sub, one topic per fly
        +----------+---------+----------+----------+
        v          v         v          v          v
   +---------+ +---------+ +---------+ +---------+ +---------+
   |  fly:   | |  fly:   | |  fly:   | |  fly:   | |  fly:   |
   |  drums  | |  bass   | |  sax    | |  piano  | | singer  |   one process each
   +----+----+ +----+----+ +----+----+ +----+----+ +----+----+   MLX LIF engine
        |           |           |           |           |         full brain (studio)
        +-----------+-----------+-----------+-----------+
                             | spike chunks + motor readouts, 10 ms
                    +--------v---------+
                    |     mapper       |   readouts -> MIDI, chart-constrained
                    +--------+---------+
                             v
                    +------------------+
                    |   take bundle    |   audio render, MIDI, binned activity,
                    +--------+---------+   motor signals, manifest
                             v
                    +------------------+
                    |      stage       |   the web page
                    +------------------+
```

**Sim engine.** Reuse `Kisame76/mlx-lif-engine` (MLX with custom Metal CSR
kernel, validated bit-for-bit against Brian2, 1.17 s per biological second on
the full MaleCNS on an M4 Pro). Shiu parameters. Our contribution is brain
packing, external input injection and per-chunk export, not a new solver.
Because nothing is live, there is no real-time constraint on the simulation
at all; a take can take as long as it needs.

**Studio take.** Each fly runs the **full 166,700-neuron brain**. A three
minute tune costs roughly 3.5 minutes of wall time per fly on the M3 Pro, so a
five fly take is under 20 minutes. Flies run sequentially per grid step so
coupling is causal: everyone's output for step n is rendered before anyone
hears it at step n+1.

**Coupling.** Fly A's motor readout is rendered to a spectral envelope (pulse
song pulses, footfalls, wingbeats). The conductor turns that envelope into
Poisson rates on Fly B's `JO-A*` (higher frequencies) and `JO-B*` (lower)
afferents, scaled into the 100 to 500 Hz band flies hear. Who hears whom is a
small matrix in the tune file.

**Time scaling.** Sim runs at biological time. Fly rhythms (wingbeat ~200 Hz,
pulse song ~28 Hz interpulse) are far above musical rates, so readouts bin
spikes to 10 ms and the mapper reads bins on the conductor's grid (16ths or
swing 8ths), one grid step ahead.

**Music.** Chord and scale pitch sets per bar from `music21`; readouts index
into the current set. **Melody:** familiar tunes carry the head as ABC or MIDI.
During the head the soloist's pitch sequence is the melody and the fly decides
whether each note sounds, its velocity, its articulation (pulse short and
accented, sine legato), and whether it pushes or lays back. The head is also
played into every fly's ears on the way in. During solos the melody drops out.
Audio is rendered offline from the MIDI with a fixed SoundFont so takes are
reproducible; GarageBand or Ableton can re-voice the MIDI for a nicer mix.

## 6. Repository layout (target)

```
.
├── docs/                 plan.md, reference.md, tune notes, rig mapping notes
├── data/                 gitignored; fetched feathers + packed brains
├── fruitless/            Python package (uv, Python 3.12)
│   ├── data/             fetch, filter, sign assignment, packing
│   ├── sim/              wrapper over mlx-lif-engine; input injection; chunk export
│   ├── flies/            one module per role: neuron selection + motor readout
│   ├── conductor/        clock, chart, melody, form, coupling, ZeroMQ bus
│   ├── mapper/           readouts -> MIDI; chart-constrained pitch sets
│   └── render/           MIDI -> audio (SoundFont), bundle writer
├── stage/                web page: Vite + TypeScript + three.js
│   ├── src/              loader, sync, brain layers, rig driver, camera, transport
│   ├── assets/           fly.glb, instruments, hero meshes (built, not committed)
│   └── public/takes/     bundles for the published site
├── tunes/                YAML: chart, melody, form, roles, coupling
├── takes/                gitignored local recordings
├── tests/
└── scripts/              fetch-data, pack-brain, studio-take, build-stage
```

`.tool-versions`: `python 3.12.x`, `nodejs 22`. CI runs `uv run pytest` on
the pure Python parts and `npm run build` on the stage; the MLX kernel path
is tested locally only.

## 7. Phases

Each phase ends with something you can open in a browser.

### Phase 0: data and one brain (week 1)
- Fetch the three feathers (annotations 14.5 MB, neurotransmitters 43 MB,
  weights 1.05 GB) with a SHA-256 lock file.
- Filter to `status == 'Traced'`, join `consensus_nt` on `body`, assign signs
  (ACh +1, GABA/Glu -1; document histamine and monoamines as a config switch).
- Pack the full brain for `mlx-lif-engine`; reproduce Shiu's sugar to `MN9`
  result and a `R1-R6` step driving `DNp01`.
- **Done when:** one full-brain sim runs from our package and writes a chunked
  activity file in the bundle format. **Done 2026-09-18**, see `docs/log.md`.

### Phase 1: the stage skeleton with one silent fly (week 2)
- Vite + three.js page that loads a bundle, draws 166,700 soma points from
  `malecns-v1.0-soma-points`, and colors them from the activity chunks while
  scrubbing a transport. No audio yet, no body.
- Hero mesh pipeline: fetch the sax circuit meshes via `navis` and
  `cloud-volume`, convert to glTF, draw on top.
- **Done when:** you can scrub through phase 0's recording in the browser and
  watch the driven circuit light up on the mesh layer. **Done 2026-09-19**
  with the sweet GRN to `MN9` pathway (DNp01 is silent under that drive);
  see `docs/log.md`.

### Phase 2: the sax plays the head (weeks 3-4)
- Sax fly: drive `pC1_*` and confirm `pIP10`, `vPR6`, `dPR1`, `TN1*` and wing
  MNs follow. Readout: pulse vs sine, intensity.
- Conductor with clock, chart, melody loader, form state machine. Mapper to
  MIDI. Offline audio render. First full bundle.
- Stage: audio element as clock, transport with waveform and form markers,
  MIDI notes shown and linked to the readout neurons that fired.
- **Done when:** the page plays a sax head over changes, and the wing MN
  meshes light in time with the notes you hear. **Done 2026-09-19** with a
  72 second blues (head, one sax chorus, head) and an original test head;
  see `docs/log.md`. Audio is rendered by a small deterministic additive
  synth so a take's sound rebuilds from its notes; a SoundFont path via
  tinysoundfont (which has an offline `generate`) is the upgrade if wanted.

### Phase 3: bodies (weeks 5-6)
- Fly model: six legs, wings, head, antennae, proboscis, abdomen. Stylised,
  not photoreal. Built procedurally in three.js (chosen over a Blender glTF so
  there are no asset files and joints are plain Groups). Instruments as props.
- Rig driver: motor readouts to joint angles, one mapping module per role,
  displayed on the page.
- **Done when:** the sax fly stands on stage, extends one wing and vibrates
  it while the head plays, and startles when `DNp01` fires. **Done
  2026-09-19** as a procedural three.js body rather than a Blender asset; the
  startle rule is in the rig but no take has fired DNp01 yet. See
  `docs/log.md`.

### Phase 4: the rhythm section (weeks 7-8)
- Bass and drums flies, their readouts, their rig mappings, their meshes.
- Coupling: sax to rhythm section ears, and back.
- Stage: bandstand layout, camera that follows the solo, per-fly brain panels.
- **Design change from the probe** (`docs/log.md`, "what moves the legs?"):
  descending walking commands do not move leg motor neurons in this model,
  because their strongest inputs are inhibitory premotor interneurons and the
  model has no pattern generator. Each leg's excitatory premotor pool, derived
  from the pack, does move that leg selectively. So the conductor drives the
  tripod pools in alternation on the beat, and the page says the gait timing
  is the conductor's while which motor neurons fire, how hard, and the
  crosstalk are the fly's. Wings respond to any drive, so the drummer runs on
  steering descending neurons plus what it hears, with voices split by muscle
  type (power vs steering) since left and right were symmetric.
- **Done when:** a three fly take of a blues plays head in, one chorus, head
  out; the bass fly's legs walk the line; the bass fly's `JO-*` meshes light
  when the sax plays. **Done 2026-09-19**; ears read on the strip rather than
  as meshes. See `docs/log.md`.

### Phase 5: the pianist, the mushroom body and free style (weeks 9-10)
- Piano fly on the central complex bump; chart changes rotate the bump.
- Dopaminergic reward gating readout gain when a consonance check passes.
- First free-style tune with no chart and no melody.
- **Design change from the probe** (`docs/log.md`, "does the ring hold a
  bump?"): the ring's wiring is present but the LIF has no persistent
  activity, so a bump lasts only while driven. The conductor writes the chord
  root into the ring as a driven EPG wedge (a landmark setting heading) and the
  fly reads the population vector back; in free style only the ear imbalance
  pushes PEN_a left and right, and the key the ring points at at each bar line
  becomes the band's chord. Reward: PAM dopaminergic neurons are driven when
  the soloist's last note is a chord tone on a beat, PPL1 when it is outside
  the scale; MBON rate relative to baseline scales the piano's velocity.
- **Done when:** a four fly standard plays its head recognisably and solos on
  the changes; a free-style take shows the EPG bump wandering on the page.
  **Done 2026-09-19**; the wander shows as the key the caption names each bar
  and in the pianist's head yaw. See `docs/log.md`.

### Phase 6: publish (week 11)
- Data budget met, bundles chunked, site on GitHub Pages or the cluster.
- README with honest scope, a link to the page, a reproducible seed.
  CC-BY attribution for MaleCNS. Submit to `awesome-fly`.

### Stretch
- **Singer:** FlyWire v783 female as a sixth fly; male song to her `JO-*`, her
  `pC1*`/`vpoDN` receptivity decides whether the tune resolves. Male-to-male
  ring coupling as the flagship free-style format.
- **Explorer:** click any neuron on the page and see its full connectivity
  in this take.

## 8. Tune format

```yaml
name: fly-me-to-the-moon
tempo_bpm: 120
grid: swing8       # or 16th
key: C
form: [head, solo:sax, solo:piano, trade4:[sax, piano], head]
chart:             # one list per bar
  - [Am7, Am7, Dm7, Dm7]
  - [G7, G7, Cmaj7, Cmaj7]
  - [Fmaj7, Fmaj7, Bm7b5, E7]
  # ...
melody: melody.abc # ABC or MIDI; the head the soloist plays and every fly hears first
roles: [drums, bass, sax, piano]
coupling:          # who hears whom, gain 0..1
  sax:   {bass: 0.6, drums: 0.4, piano: 0.5}
  bass:  {drums: 0.8, sax: 0.3}
  drums: {bass: 0.8}
  piano: {sax: 0.7, bass: 0.4}
free_style: false
```

Free-style tunes set `chart: []`, omit `melody`, and set `free_style: true`;
their form is open and ends when the operator stops the take, or when the
singer accepts in the stretch phase. This simulates a live performance, and
standards get played at gigs every night. If a take is published as a
recording, prefer public-domain standards for that take; the 1930 catalogue
entered the US public domain in January 2026.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Role circuit is silent or saturates under drive | Reproduce Shiu's MN9 result first; sweep Poisson rate per fly and store the operating point in the fly module |
| Bundle too large for a static page | Sparse event lists, 50 ms soma bins, 10 s chunks, hero layer only at 10 ms; fall back to 100 ms soma bins |
| 166,700 points x 5 flies too heavy in the browser | One `Points` object per fly with a color attribute updated per frame; shrink non-soloists; test on an integrated GPU early |
| Fly rig and instruments are an art project | Stylised low-poly model, procedural driving so no keyframes are needed; source a CC fly model as a starting point; scope it to phase 3 only |
| Body animation looks disconnected from the music | Same readout drives both; show the readout on the page so the link is inspectable |
| Music is unlistenable | Pentatonic constraint, rate to velocity, one-grid look-ahead; treat as a mapper problem |
| Neurotransmitter sign for 11.6k unclear neurons | Follow Shiu (monoamines excitatory) by default, expose as a config switch, record the choice in the manifest |

## 10. Immediate next steps

1. Pin `python 3.12` and `nodejs 22` in `.tool-versions`; `uv init` the
   package; `npm create vite` the stage.
2. `scripts/fetch-data` with SHA-256 lock file.
3. Run `mlx-lif-engine`'s own MaleCNS example end to end.
4. Draw 166,700 soma points in three.js from the released soma-point layer.
