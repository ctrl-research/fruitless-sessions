from pathlib import Path

from fruitless.data.sources import load_lock, verify


def test_lock_has_three_tables():
    lock = load_lock(Path(__file__).resolve().parents[1] / "data" / "sources.lock.json")
    assert set(lock) == {"annotations", "neurotransmitters", "connectivity"}
    for s in lock.values():
        assert len(s.sha256) == 64 and s.bytes > 0 and s.url.endswith(s.name)


def test_verify_false_when_missing(tmp_path):
    lock = load_lock(Path(__file__).resolve().parents[1] / "data" / "sources.lock.json")
    assert verify(lock["annotations"], tmp_path) is False
