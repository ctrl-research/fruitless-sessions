import numpy as np
import pyarrow as pa

from fruitless.flies.select import Resolver, Selection


def _table():
    return pa.table({
        "bodyId": pa.array([10, 20, 30, 40, 50], pa.int64()),
        "type": ["JO-A1", "JO-B2", "Ti flexor MN", "DNp01", None],
        "instance": ["JO-A1_L", "JO-B2_R", "Ti flexor MN_L", "DNp01(GF)_R", None],
        "superclass": ["cb_sensory", "cb_sensory", "vnc_motor", "descending_neuron", None],
        "class": ["mechanosensory", "mechanosensory", None, None, None],
        "subclass": ["auditory", "auditory", "fl", None, None],
        "somaSide": [None, None, "L", "R", None],
        "rootSide": ["L", "R", None, None, None],
        "status": ["Traced"] * 5,
        "fruDsx": [None] * 5,
        "dimorphism": [None] * 5,
        "flywireType": [None] * 5,
        "somaNeuromere": [None] * 5,
        "somaLocation": [None] * 5,
    })


def test_selection_by_type_regex_and_side():
    t = _table()
    r = Resolver(np.array([10, 20, 30, 40]), t)   # pack excludes the null-superclass row
    assert r.indices(Selection("ears", types=(r"JO-A.*", r"JO-B.*"))).tolist() == [0, 1]
    assert r.indices(Selection("left_ears", types=(r"JO-.*",), side="L")).tolist() == [0]
    assert r.indices(Selection("gf", types=(r"DNp01",))).tolist() == [3]
    assert r.indices(Selection("fl", superclasses=("vnc_motor",), subclass=("fl",))).tolist() == [2]
    assert r.types_of(np.array([2])) == ["Ti flexor MN"]


def test_selection_exclude():
    r = Resolver(np.array([10, 20, 30, 40]), _table())
    sel = Selection("not_b", types=(r"JO-.*",), exclude=(r"JO-B.*",))
    assert r.indices(sel).tolist() == [0]
