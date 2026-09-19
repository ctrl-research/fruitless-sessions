# Reference: MaleCNS data, circuits, simulation and tooling

Facts verified on 2026-09-18 against the release files and project sources.
"[file]" means the value was read from the actual v1.0 feather files;
"[src]" means from a linked page or repository. Re-check before relying on
anything marked "unverified".

## 1. Dataset

- FlyEM male CNS. v0.9 released 2025-10-05, **v1.0 released 2026-06-08**,
  Cell paper 2026-09-03 (Berg, Beckett, Costa, Schlegel et al., "Sexual
  dimorphism in the complete Drosophila male central nervous system
  connectome"). License CC-BY 4.0. [src]
  - https://male-cns.janelia.org/release/
  - https://male-cns.janelia.org/download/
  - https://www.cell.com/cell/fulltext/S0092-8674(26)00942-6
  - Open preprint text: https://pmc.ncbi.nlm.nih.gov/articles/PMC12636603/
- Counts: 166,700 neurons, 11,710 types, ~125 M synaptic connections (Cell);
  preprint says 166,691 / 11,691 / 25.6 M edges between 166,391 neurons.
- neuPrint dataset string: **`male-cns:v1.0`** at https://neuprint.janelia.org
  (token required; `NEUPRINT_APPLICATION_CREDENTIALS` for Python). [src]

### Flat files (no auth), bucket `gs://flyem-male-cns`

Base: `https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/`
All Apache Arrow Feather. [src: bucket listing]

| File | Size | Key columns |
|---|---|---|
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 14.5 MB, 211,577 rows | `bodyId, type, instance, superclass, class, subclass, somaSide, rootSide, status, statusLabel, fruDsx, dimorphism, flywireType, hemibrainType, mancType, itoleeHl, trumanHl, somaNeuromere, entryNerve, exitNerve, somaLocation, ...` |
| `body-neurotransmitters-male-cns-v1.0.feather` | 43.3 MB, 1,835,518 rows | `body, cell_type, predicted_nt, predicted_nt_confidence, celltype_predicted_nt, consensus_nt, ...` |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 1.05 GB | `body_pre, body_post, weight` (weight = synapse count, no minimum) |
| `body-stats-...feather` | 778 MB | per-body synapse counts |
| `syn-partners-...feather` | 6.8 GB | synapse pairs with coordinates and `primary_post` ROI |
| `syn-points-...feather` | 13.1 GB | individual pre/post points |
| `tbar-neurotransmitters-...feather` | 2.65 GB | per-presynapse NT probabilities |

`-traced-only` and `-significant-only` weight variants exist in the bucket;
their definitions are undocumented (unverified).

Join keys differ: `bodyId` (annotations, neuPrint) vs `body` (NT file) vs
`body_pre`/`body_post` (weights). bodyId is int64, non-contiguous,
10,001 to 1,571,825,087.

Other assets:
- Neuroglancer scene: `https://neuroglancer-demo.appspot.com/#!gs://flyem-male-cns/v1.0/male-cns-v1.0.json`
- Segmentation: `precomputed://gs://flyem-male-cns/v1.0/segmentation`
- Meshes: `precomputed://gs://flyem-male-cns/v1.0/segmentation/meshes-malecns/single-res-meshes`
- Skeletons SWC: `gs://flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/`
- Soma points: `precomputed://gs://flyem-male-cns/v1.0/malecns-v1.0-soma-points`
- ROI meshes: `precomputed://gs://flyem-male-cns/rois/fullbrain-roi-v5`, `.../malecns-vnc-neuropil-roi-v0`
- Full Neo4j DB and neuPrint input CSVs: `gs://flyem-male-cns/v1.0/database/`
- Community HF mirror: https://huggingface.co/QuixiAI/MaleCNS
- Cell Type Explorer pages: `https://reiserlab.github.io/celltype-explorer-drosophila-male-cns/types/<type>.html`

### Filtering to neurons [file]

`status` values: Traced 165,122 · Orphan 15,925 · Glia 11,864 · Unimportant
10,751 · Assign 1,832 · Anchor 611 · null 5,472. Hobby ports keep rows with
non-null `superclass` and get 166,700. Use `status == 'Traced'` or non-null
`superclass`; document which.

`superclass` (brain vs VNC is the prefix; there is no region column):
`ol_intrinsic` 89,403 · `cb_intrinsic` 32,164 · `vnc_intrinsic` 13,161 ·
`visual_projection` 9,201 · `vnc_sensory` 6,370 · `ol_sensory` 6,098 ·
`cb_sensory` 4,868 · `ascending_neuron` 1,846 · `descending_neuron` 1,314 ·
`vnc_motor` 708 · `visual_centrifugal` 563 · `sensory_ascending` 537 ·
`cb_motor` 107 · `vnc_efferent` 94 · `cb_endocrine` 72 · plus small classes
and `*_tbc` variants.

`class` (sparse, filled only for some populations): `Kenyon_Cell` 4,064 ·
`CX` 2,950 · `DAN` 340 · `MBON` 97 · `olfactory`, `mechanosensory`,
`gustatory`, `ALPN`, `visual`, ...

`subclass`: sensory modality (`auditory` 115, `chordotonal organ`,
`wind_gravity`, ...) and leg for motor neurons (`fl`/`ml`/`hl`).

`fruDsx` values: `fru_high` 2,611 · `fru_low` 1,989 · `coexpress_high` 193 ·
`coexpress_low` 65 · `dsx_high` 138 · `dsx_low` 16 · null. high/low is
annotation confidence. fru+ = any `fru_*` or `coexpress_*`.

`dimorphism` values: `male-specific` 1,258 · `sexually dimorphic` 771 ·
`potentially sexually dimorphic` 177 · `potentially male-specific` 162 ·
null (isomorphic or not assessed; no explicit isomorphic string).

`consensus_nt` values: acetylcholine 104,193 · glutamate 29,443 · gaba 22,196
· histamine 8,024 · dopamine 396 · octopamine 101 · serotonin 48 · unclear
1,671,117 (mostly fragments). About 11.6k of the 166.7k neurons have no
usable sign.

## 2. Cell type names for the ensemble [file]

Query by exact `type`, or regex on `type`. `instance` is `type_L` / `type_R`.
Many VNC names contain spaces and punctuation; quote them.

- **Auditory afferents** (`superclass=cb_sensory`, `class=mechanosensory`,
  672 bodies, 34 types): `JO-A1..JO-A4`, `JO-B1_a/b/c`, `JO-B2`, `JO-B3`,
  `JO-B4_a/b`, `JO-CA1/2`, `JO-CL`, `JO-CM`, `JO-DA`, `JO-DP`, `JO-ED*`,
  `JO-EV1..6`, `JO-FD1/2`, `JO-FV`, `JO-mz`. Downstream: `AMMC-A1`,
  `AMMC001..AMMC038` (`cb_intrinsic`). No literal `aPN1` type.
- **Courtship song**: `pC1_1a .. pC1_19` with a/b/c/d splits (male-specific,
  `dsx_high`/`coexpress_*`); female-homologous `pC1x_a..d`
  (`flywireType` `pC1a,pC1c` / `pC1b`). No literal `P1` type. `pIP10`
  (2, descending, fru_high, male-specific); `vPR6` (8), `dPR1` (2),
  `TN1a_a..i`, `TN1c_a..d` (35, all coexpress_high).
- **Wing motor neurons** (`vnc_motor`): `DLMn a, b`, `DLMn c-f`,
  `DVMn 1a-c`, `DVMn 2a, b`, `DVMn 3a, b`, `b1 MN`, `b2 MN`, `b3 MN`,
  `hg1 MN` (fru_high, dimorphic), `hg2 MN`, `hg3 MN`, `hg4 MN`, `i1 MN`,
  `i2 MN`, `iii1 MN`, `iii3 MN`, `ps1 MN` (fru_high), `ps2 MN`, `tp1 MN`,
  `tp2 MN`, `tpn MN`.
- **Leg motor neurons** (`vnc_motor`, leg via `subclass`): `Ti flexor MN`
  (37), `Ti extensor MN`, `Tr flexor MN`, `Tr extensor MN`, `Fe reductor MN`,
  `Sternotrochanter MN`, `Sternal anterior rotator MN`,
  `Sternal posterior rotator MN`, `Tergopleural/Pleural promotor MN`,
  `Pleural remotor/abductor MN`, `Tergotr. MN`, `Ta depressor MN`,
  `Ta levator MN`, `ltm MN`, `ltm1-tibia MN`, `ltm2-femur MN`.
- **Walking descending neurons**: `DNp09`, `DNa02`, `MDN` (4), `DNa01`,
  `DNg11`, `DNp20`, `DNpe017`.
- **Giant fiber**: `DNp01` (instance `DNp01(GF)_L/R`), VNC partners
  `GFC1..GFC4`.
- **Mushroom body**: KCs by `class=Kenyon_Cell` (`KCg-m` 1,342, `KCab-*`,
  `KCa'b'-*`, `KCg-d`, `KCg-s1..s4`); `MBON01..MBON35` (+ `-like`);
  DANs `PAM01..PAM15` (316), `PPL101..PPL108`; also `OA-VPM3/4`.
- **Central complex** (`class=CX`): `EPG` (46), `EPGt` (4),
  `PEN_a(PEN1)` (20), `PEN_b(PEN2)` (22), `Delta7` (42).
- **Clock**: `s-LNv` (8), `l-LNv` (8), `5thsLNv_LNd6`, `LNd_b`, `LNd_c`,
  `DN1a` (4), `DN1pA` (8), `DN1pB` (4).
- **Photoreceptors / taste** (used by ports for validation): `R1-R6`
  (3,377), `R7*`, `R8*`, `MN9` (2, `cb_motor`).

## 3. Simulation recipe

### Shiu et al. 2024 (Nature 634:210) reference model [src]

- Code: https://github.com/philshiu/Drosophila_brain_model (Brian2)
- Open text: https://pmc.ncbi.nlm.nih.gov/articles/PMC11446845/
- Equations: `dv/dt = (v_0 - v + g) / t_mbr` (unless refractory);
  `dg/dt = -g / tau` (unless refractory).
- Parameters: `t_mbr = 20 ms`, `v_0 = v_rst = -52 mV`, `v_th = -45 mV`,
  `t_rfc = 2.2 ms`, `t_dly = 1.8 ms`, `tau = 5 ms`, **`w_syn = 0.275 mV`
  per synapse** (the one tuned parameter), default Poisson drive 150 Hz,
  dt 0.1 ms.
- Weight: `w_ij = synapse_count * sign * w_syn`.
- Sign rule: ACh excitatory; GABA and glutamate inhibitory; dopamine,
  octopamine, serotonin excitatory. Sign assigned per neuron, not per synapse.

### How the MaleCNS ports differ [src]

| Project | Framework | Sign for other NTs | Notes |
|---|---|---|---|
| Kisame76/drosophila-brain-mlx + mlx-lif-engine | MLX, custom Metal CSR kernel, 2 dispatches per tick | histamine/monoamines/unclear -> 0, outgoing edges dropped | Shiu params exactly; validated vs Brian2 float64; FlyWire full brain 0.29 s per bio-second, **MaleCNS full brain 1.17 s per bio-second** on M4 Pro; peak memory 665 MB; Python >= 3.11, uv |
| nftechie/doomfly | C++ kernel via ctypes | GABA/Glu/histamine -1, unclear +1 | Shiu params; 25,582,938 edges; SHA-256 lock file for data |
| seohyunjun/mps-malecns-model | PyTorch MPS, gather + index_add | others 0 | Not Shiu: dimensionless LIF, dt 1 ms, no refractory/delay; 44.6 steps/s full brain |
| Apolotary/fly-lab | JS, vendored DesktopFly 1,045-neuron locomotor circuit | others 0 | Six leg rates -> softmax gesture policy -> MIDI to Ableton; not spike-to-note |

Brian2 Cython on the full FlyWire brain: 2.07 s per bio-second (M4 Pro).
Dense MLX: 19.55 s. Dense is not viable; sparse CSR is the path.

### Apple Silicon constraints [src]
- PyTorch MPS has no sparse tensors (https://github.com/pytorch/pytorch/issues/129842).
- MLX has no native sparse matrices; use a custom `mx.fast.metal_kernel` as
  the MLX engine does.
- Extrapolated, unverified: a 5 M edge subgraph should run about 10x real
  time at dt 0.1 ms on the MLX engine.

## 4. Music and visualization tooling [src]

### MIDI / OSC
- `mido` 1.3.3 + `python-rtmidi` 1.5.8: `mido.open_output(name, virtual=True)`
  makes a virtual CoreMIDI port on macOS. Or enable the IAC Driver in Audio
  MIDI Setup.
- `python-osc` 1.10.2 for SuperCollider, Sonic Pi, Pure Data.
- Ableton Link from Python: `aalink` (asyncio); `isobar` 0.2.1 can sync to
  Link and schedule patterns to MIDI/OSC.
- `music21` 10.5.0 for chord and scale pitch sets (offline).
  `pretty_midi` 0.2.11 for logging takes. `mingus` is unmaintained.
- Prior spike sonification (ViSoND, Smear Lab): one pitch per neuron,
  pentatonic restriction, fixed velocity, one track per event type.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC13041969/

### Visualization
- `neuroglancer` Python 2.41.2: `SegmentationLayer.segment_colors`
  (`segmentColors`) set inside `viewer.txn()`. No per-segment shader LUT yet
  (https://github.com/google/neuroglancer/issues/259). Each txn serializes
  the whole map; throttle to about 5 Hz on thousands of segments.
- `navis` 1.12.0 + `octarine3d` 0.8.0 (pygfx/WGPU): `Viewer.set_colors`,
  `Viewer.colorize`, `octarine-navis-plugin` `add_neurons(color_by=...)`.
  `navis.interfaces.neuprint.fetch_mesh_neuron` needs `cloud-volume`.
- `neuprint-python` 0.6.3: `fetch_skeleton(bodyId, heal=True)`.
- Browser precedents: snedea/flybrain (LIF in a Web Worker, WebGL raster
  grouped by region); abgnydn/webgpu-fly (fused WGSL LIF over CSR, three.js,
  ~0.25 kHz biological time on M2 Pro).
- 2D streaming: Rerun (`rerun-sdk`) handles kHz series at 60 fps with
  < 30 ms latency on M1; Bokeh server slows as sources grow.

## 5. Female brain (phase 5) [src]
- FlyWire v783 connectivity: `Connectivity_783.parquet` in Shiu's repo.
- Type matching: MaleCNS `flywireType` column (8,199 distinct values,
  comma-joined when ambiguous) and flyconnectome `flywire_annotations`
  v3.0.0+ (adds `dimorphism`, `fru_dsx`, `supertype`).
  https://github.com/flyconnectome/flywire_annotations
- cocoa `1_malecns_flywire_mapping.ipynb` does the mapping programmatically.
  https://github.com/flyconnectome/cocoa
- DesktopFly already co-runs FlyWire v783 and a MaleCNS leg circuit with an
  explicit cross-specimen activity bridge (not a synapse).
  https://github.com/DenisSergeevitch/desktop-fly

## 6. Local machine (2026-09-18)
Apple M3 Pro, 36 GB, 18 GPU cores. mise with Python 3.12.13 and 3.13.x
available, uv 0.11, Node 22.15. GarageBand installed; no Ableton or
SuperCollider yet.
