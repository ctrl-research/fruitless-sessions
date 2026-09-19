"""Session parity with the engine's own run(): same draws, same spikes."""

import numpy as np
import pytest

from fruitless import paths

pytestmark = pytest.mark.sim


@pytest.fixture(scope="module")
def engine():
    core = pytest.importorskip("lif.core", exc_type=ImportError)
    engine_fused = pytest.importorskip("lif.engine_fused", exc_type=ImportError)
    if not (paths.PACK / "manifest.json").is_file():
        pytest.skip("MaleCNS pack not compiled; run `fruitless pack`")
    return core, engine_fused, core.load_pack(paths.PACK)


def test_session_matches_engine_run(engine):
    core, engine_fused, pack = engine
    from fruitless.sim.session import Session

    n_ticks = 1500
    stim = core.make_stimulus(pack, n_ticks=n_ticks, seed=7, n_targets=50, rate_hz=150.0)
    ref = engine_fused.run(pack, stim, chunk=32, edge_split=8, record=True, warmup=0)

    s = Session(pack, stim.targets, edge_split=8)
    draws = np.asarray(stim.draws)
    # split unevenly to exercise chunk boundaries and the delay ring across steps
    a = s.step(draws[:700])
    b = s.step(draws[700:1234])
    c = s.step(draws[1234:])
    events = np.concatenate([a.events, b.events, c.events])
    events = events[np.lexsort((events[:, 1], events[:, 0]))]

    assert s.t == n_ticks
    assert np.array_equal(s.total_counts(), ref.spike_counts)
    assert np.array_equal(events, ref.events)
    assert ref.total_spikes() > 0
