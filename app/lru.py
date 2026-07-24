import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Node:
    key: str
    value: Any
    expires_at: Optional[float] = None 
    prev: "Optional[Node]" = None
    next: "Optional[Node]" = None


@dataclass
class Stats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    sets: int = 0
    deletes: int = 0


class LRUCache:
    def __init__(self, capacity: int = 128):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._map: dict[str, Node] = {}
        self._lock = threading.RLock()
        self.stats = Stats()

        self._head = Node(key="__head__", value=None)
        self._tail = Node(key="__tail__", value=None)
        self._head.next = self._tail
        self._tail.prev = self._head  

    def _remove(self, node: Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _insert_at_head(self, node: Node) -> None:
        node.next = self._head.next
        node.prev = self._head
        self._head.next.prev = node
        self._head.next = node

    def _move_to_head(self, node: Node) -> None:
        self._remove(node)
        self._insert_at_head(node)

    def _evict_tail(self) -> None:
        lru_node = self._tail.prev
        if lru_node is self._head:
            return 
        self._remove(lru_node)
        del self._map[lru_node.key]
        self.stats.evictions += 1

    def _is_expired(self, node: Node) -> bool:
        return node.expires_at is not None and node.expires_at <= time.time()


    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.stats.misses += 1
                return None
            if self._is_expired(node):
                self._remove(node)
                del self._map[key]
                self.stats.expirations += 1
                self.stats.misses += 1
                return None
            self._move_to_head(node)
            self.stats.hits += 1
            return node.value

    def put(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        with self._lock:
            expires_at = time.time() + ttl_seconds if ttl_seconds else None
            existing = self._map.get(key)
            if existing is not None:
                existing.value = value
                existing.expires_at = expires_at
                self._move_to_head(existing)
                self.stats.sets += 1
                return

            node = Node(key=key, value=value, expires_at=expires_at)
            self._map[key] = node
            self._insert_at_head(node)
            self.stats.sets += 1

            if len(self._map) > self.capacity:
                self._evict_tail()

    def delete(self, key: str) -> bool:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                return False
            self._remove(node)
            del self._map[key]
            self.stats.deletes += 1
            return True

    def sweep_expired(self) -> int:
        """Actively remove all expired keys. Returns count removed."""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, n in self._map.items() if n.expires_at is not None and n.expires_at <= now]
            for k in expired_keys:
                node = self._map[k]
                self._remove(node)
                del self._map[k]
                self.stats.expirations += 1
            return len(expired_keys)

    def snapshot(self) -> list[dict]:
        """Return current keys in MRU -> LRU order, for the dashboard/persistence."""
        with self._lock:
            out = []
            node = self._head.next
            while node is not self._tail:
                out.append({
                    "key": node.key,
                    "value": node.value,
                    "expires_at": node.expires_at,
                })
                node = node.next
            return out

    def __len__(self) -> int:
        with self._lock:
            return len(self._map)
