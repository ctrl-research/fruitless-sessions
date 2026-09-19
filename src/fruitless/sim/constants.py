"""Time constants shared by modules that must not import the Metal engine.

The engine's tick is 0.1 ms (`lif.core.DT`). `tests/test_constants.py` checks
this file agrees with it whenever the engine is importable.
"""

DT_MS = 0.1
TICKS_PER_MS = 10
