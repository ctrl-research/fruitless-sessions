import numpy as np

from fruitless.recording.activity import ActivityWriter, bin_events, read_chunk, write_chunk
from fruitless.sim.constants import TICKS_PER_MS


def test_bin_events_round_trip(tmp_path):
    # 3 neurons, 10 ms bins, 2 bins; neuron 1 fires 3 times in bin 0, neuron 2 once in bin 1
    ev = np.array([[0, 1], [5, 1], [99, 1], [100, 2], [250, 0]], dtype=np.int32)  # tick 250 is bin 2 -> dropped
    chunk = bin_events(ev, t0_tick=0, n_bins=2, bin_ms=10, n_neurons=3)
    dense = chunk.dense()
    assert dense.tolist() == [[0, 3, 0], [0, 0, 1]]
    p = tmp_path / "c.bin"
    write_chunk(p, chunk)
    back = read_chunk(p)
    assert back.bin_ms == 10 and back.n_neurons == 3 and back.n_bins == 2
    assert np.array_equal(back.dense(), dense)


def test_bin_events_remap_and_saturation():
    ev = np.array([[0, 7]] * 300 + [[0, 3]], dtype=np.int32)
    remap = np.full(10, -1, dtype=np.int64)
    remap[7] = 0
    chunk = bin_events(ev, 0, 1, 10, n_neurons=1, remap=remap)
    assert chunk.dense().tolist() == [[255]]


def test_writer_chunks_and_partial_tail(tmp_path):
    bin_ms, chunk_s = 10, 0.05          # 5 bins per chunk, 500 ticks per chunk
    w = ActivityWriter(tmp_path, bin_ms, chunk_s, n_neurons_pack=4)
    # step 1: 300 ticks, a spike at tick 10 (bin 0) on neuron 2
    w.add(np.array([[10, 2]]), 300)
    # step 2: 300 ticks (total 600): spikes at 450 (bin 4 of chunk 0), 520 (bin 0 of chunk 1)
    w.add(np.array([[450, 3], [520, 1]]), 300)
    meta = w.close()
    assert meta["n_chunks"] == 2 and meta["n_bins"] == 6
    c0 = read_chunk(tmp_path / "chunk_0000.bin")
    c1 = read_chunk(tmp_path / "chunk_0001.bin")
    assert c0.n_bins == 5 and c1.n_bins == 1
    assert c0.dense()[0, 2] == 1 and c0.dense()[4, 3] == 1
    assert c1.dense()[0, 1] == 1
    assert TICKS_PER_MS == 10


def test_fsm_round_trip(tmp_path):
    from fruitless.recording.meshes import read_fsm, write_fsm
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    f = np.array([[0, 1, 2]], dtype=np.uint32)
    write_fsm(tmp_path / "m.fsm", v, f)
    v2, f2 = read_fsm(tmp_path / "m.fsm")
    assert np.array_equal(v, v2) and np.array_equal(f, f2)
