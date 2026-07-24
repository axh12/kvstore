import tempfile
from pathlib import Path

from app.lru import LRUCache
from app.persistence import SnapshotManager


def test_save_and_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snap.json"

        cache1 = LRUCache(capacity=10)
        cache1.put("a", 1)
        cache1.put("b", {"nested": True})
        mgr1 = SnapshotManager(cache1, path=str(path))
        mgr1.save()

        cache2 = LRUCache(capacity=10)
        mgr2 = SnapshotManager(cache2, path=str(path))
        loaded = mgr2.load()

        assert loaded == 2
        assert cache2.get("a") == 1
        assert cache2.get("b") == {"nested": True}


def test_load_missing_file_returns_zero():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "does_not_exist.json"
        cache = LRUCache(capacity=10)
        mgr = SnapshotManager(cache, path=str(path))
        assert mgr.load() == 0


def test_expired_keys_not_resurrected():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snap.json"
        cache1 = LRUCache(capacity=10)
        cache1.put("short", "lived", ttl_seconds=-1)  # already expired
        mgr1 = SnapshotManager(cache1, path=str(path))
        # manually force save without lazy expiry cleanup interfering
        mgr1.save()

        cache2 = LRUCache(capacity=10)
        mgr2 = SnapshotManager(cache2, path=str(path))
        loaded = mgr2.load()
        assert loaded == 0