import pytest

from fruitless.sim.constants import DT_MS, TICKS_PER_MS


def test_constants_match_engine():
    core = pytest.importorskip("lif.core")
    assert DT_MS == core.DT
    assert TICKS_PER_MS == round(1.0 / core.DT)
