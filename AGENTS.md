# AGENTS.md

Operational notes for humans and AI agents working in this repository.

## Read first

`docs/plan.md` is the project plan and the source of truth for scope: the
product is a **fully static web page** playing back offline **studio takes**.
Nothing runs live. `docs/reference.md` holds the verified data schema, cell
type names and simulation parameters. `docs/log.md` is the dated journal of
what was measured.

## Stack

- Python 3.12, managed with `uv` (`uv sync --extra dev`). Versions in `.tool-versions`.
- Simulation: `mlx-lif-engine` (import `lif`), pinned to a commit in
  `pyproject.toml`. It is Apple silicon only. Our code wraps its kernels; it
  does not change tick semantics, constants or the pack format.
- Data: three MaleCNS v1.0 Feather tables under `data/raw/` (gitignored),
  hashed in `data/sources.lock.json` (tracked). The compiled pack lives in
  `data/pack/` (gitignored).
- Web page (later): Vite + TypeScript + three.js under `stage/`.

## Commands

```bash
uv run fruitless fetch-data | pack | select <regex>... | smoke
uv run pytest                 # all tests, including the GPU parity test (marker `sim`)
uv run pytest -m "not sim"    # what CI runs
uv run ruff check src tests
```

## Conventions

- Cell type names are literal MaleCNS `type` strings; selection patterns are
  full-match regexes. Verify a new type name against the annotation table
  (`fruitless select`) before writing it into a fly module.
- Model index = position in `pack.neuron_ids` (ascending bodyId). Never store
  bodyIds in activity files; store model indices and the pack's manifest hash.
- Neurotransmitter sign convention is the engine's pack default (ACh +, GABA
  and glutamate -, everything else drops its outgoing edges). Any change is a
  config switch recorded in the take manifest, never a silent edit.
- Every take is reproducible from seed, tune file, pack manifest hash and
  engine commit. If a change alters spike output, say so in `docs/log.md`.
- Honesty rule: the README and the page say plainly what a LIF connectome
  model is and where rhythm comes from. Do not write copy that implies the
  flies "learned" or "decided" anything the readouts did.
- Branch naming and commits follow `CONTRIBUTING.md` (conventional commits,
  bare SemVer). Never push to `main`.
