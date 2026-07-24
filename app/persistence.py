"""
Minimal durability layer, inspired loosely by Redis RDB snapshotting.

Every N seconds a background thread dumps the current cache contents to
a JSON file on disk. On startup, if a snapshot file exists, it is loaded
back in so the store survives a process restart. This is NOT a WAL / AOF
(no per-write durability) — it's a periodic snapshot, which is a deliberate
and explainable tradeoff between durability and write throughput.
"""

import json
import threading
import time
from pathlib import Path

from app.lru import LRUCache


class SnapshotManager:
    def __init__(self, cache: LRUCache, path: str = "snapshot.json", interval_seconds: float = 10.0):
        self.cache = cache
        self.path = Path(path)
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def load(self) -> int:
        if not self.path.exists():
            return 0
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return 0

        loaded = 0
        now = time.time()
        for entry in data:
            expires_at = entry.get("expires_at")
            if expires_at is not None and expires_at <= now:
                continue  # don't resurrect already-expired keys
            ttl_remaining = (expires_at - now) if expires_at else None
            self.cache.put(entry["key"], entry["value"], ttl_seconds=ttl_remaining)
            loaded += 1
        return loaded

    def save(self) -> None:
        data = self.cache.snapshot()
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data))
        tmp_path.replace(self.path)  # atomic on POSIX

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self.save()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.save()  # final save on shutdown