from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.lru import LRUCache
from app.persistence import SnapshotManager

CACHE_CAPACITY = 256
SNAPSHOT_PATH = "snapshot.json"
SNAPSHOT_INTERVAL_SECONDS = 10.0

cache = LRUCache(capacity=CACHE_CAPACITY)
snapshot_manager = SnapshotManager(cache, path=SNAPSHOT_PATH, interval_seconds=SNAPSHOT_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loaded = snapshot_manager.load()
    print(f"[startup] loaded {loaded} keys from {SNAPSHOT_PATH}")
    snapshot_manager.start()
    yield
    snapshot_manager.stop()


app = FastAPI(
    title="KVStore",
    description="An in-memory key-value store with LRU eviction, TTL expiry, and disk snapshotting.",
    version="1.0.0",
    lifespan=lifespan,
)


class PutRequest(BaseModel):
    value: Any = Field(..., description="Any JSON-serializable value")
    ttl_seconds: Optional[float] = Field(None, description="Optional expiry in seconds from now")


class PutResponse(BaseModel):
    key: str
    stored: bool


class GetResponse(BaseModel):
    key: str
    value: Any
    hit: bool


class StatsResponse(BaseModel):
    capacity: int
    size: int
    hits: int
    misses: int
    hit_rate: float
    evictions: int
    expirations: int
    sets: int
    deletes: int


@app.put("/keys/{key}", response_model=PutResponse)
def put_key(key: str, body: PutRequest):
    cache.put(key, body.value, ttl_seconds=body.ttl_seconds)
    return PutResponse(key=key, stored=True)


@app.get("/keys/{key}", response_model=GetResponse)
def get_key(key: str):
    value = cache.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"key '{key}' not found or expired")
    return GetResponse(key=key, value=value, hit=True)


@app.delete("/keys/{key}")
def delete_key(key: str):
    existed = cache.delete(key)
    if not existed:
        raise HTTPException(status_code=404, detail=f"key '{key}' not found")
    return {"key": key, "deleted": True}


@app.get("/keys", response_model=list[dict])
def list_keys():
    """Returns all live keys, most-recently-used first."""
    return cache.snapshot()


@app.post("/admin/sweep")
def sweep_expired():
    removed = cache.sweep_expired()
    return {"removed": removed}


@app.get("/stats", response_model=StatsResponse)
def get_stats():
    total_lookups = cache.stats.hits + cache.stats.misses
    hit_rate = (cache.stats.hits / total_lookups) if total_lookups else 0.0
    return StatsResponse(
        capacity=cache.capacity,
        size=len(cache),
        hits=cache.stats.hits,
        misses=cache.stats.misses,
        hit_rate=round(hit_rate, 4),
        evictions=cache.stats.evictions,
        expirations=cache.stats.expirations,
        sets=cache.stats.sets,
        deletes=cache.stats.deletes,
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse("static/index.html")