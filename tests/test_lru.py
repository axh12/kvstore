import time
import threading

import pytest

from app.lru import LRUCache


def test_basic_put_get():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    assert c.get("a") == 1


def test_missing_key_returns_none():
    c = LRUCache(capacity=2)
    assert c.get("nope") is None
    assert c.stats.misses == 1


def test_eviction_order():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)  # should evict "a" (least recently used)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3
    assert c.stats.evictions == 1


def test_get_refreshes_recency():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")       # "a" is now most recently used
    c.put("c", 3)     # should evict "b", not "a"
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_update_existing_key_does_not_evict():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 99)  # update, not a new insert
    assert len(c) == 2
    assert c.get("a") == 99


def test_ttl_expiry():
    c = LRUCache(capacity=2)
    c.put("a", 1, ttl_seconds=0.05)
    assert c.get("a") == 1
    time.sleep(0.1)
    assert c.get("a") is None
    assert c.stats.expirations == 1


def test_sweep_expired():
    c = LRUCache(capacity=5)
    c.put("a", 1, ttl_seconds=0.05)
    c.put("b", 2)  # no ttl
    time.sleep(0.1)
    removed = c.sweep_expired()
    assert removed == 1
    assert len(c) == 1
    assert c.get("b") == 2


def test_delete():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    assert c.delete("a") is True
    assert c.delete("a") is False
    assert c.get("a") is None


def test_snapshot_order_is_mru_first():
    c = LRUCache(capacity=3)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)
    c.get("a")  # move "a" to front
    keys_in_order = [entry["key"] for entry in c.snapshot()]
    assert keys_in_order == ["a", "c", "b"]


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        LRUCache(capacity=0)


def test_thread_safety_concurrent_writes():
    c = LRUCache(capacity=1000)

    def worker(start):
        for i in range(start, start + 200):
            c.put(f"key-{i}", i)

    threads = [threading.Thread(target=worker, args=(i * 200,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(c) == 1000
    for i in range(1000):
        assert c.get(f"key-{i}") == i