#!/usr/bin/env python3
"""
Content Delivery Network simulation.

Models:
- Edge servers and geographic distribution
- Cache lookup, hit, miss, expiry, and eviction
- Origin retrieval
- Cache-control policies
- Geographic routing
- Cache invalidation
- Health-aware edge selection
- Request metrics
- Security validation
- Failure handling
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import time
from typing import Dict, Iterable, Optional


class CacheStatus(Enum):
    HIT = "HIT"
    MISS = "MISS"
    STALE = "STALE"
    BYPASS = "BYPASS"
    ORIGIN_ERROR = "ORIGIN_ERROR"


class EdgeState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class Content:
    path: str
    body: str
    content_type: str
    version: int
    cacheable: bool = True
    ttl_seconds: int = 30

    @property
    def etag(self) -> str:
        return hashlib.sha256(
            f"{self.version}:{self.body}".encode("utf-8")
        ).hexdigest()


@dataclass
class CacheEntry:
    content: Content
    stored_at: float

    def is_fresh(self, now: float) -> bool:
        return now - self.stored_at < self.content.ttl_seconds


@dataclass
class EdgeServer:
    edge_id: str
    region: str
    capacity: int = 3
    latency_ms: int = 20
    state: EdgeState = EdgeState.HEALTHY
    cache: OrderedDict[str, CacheEntry] = field(default_factory=OrderedDict)
    hits: int = 0
    misses: int = 0
    stale: int = 0
    evictions: int = 0

    def get(self, path: str, now: float) -> tuple[CacheStatus, Optional[Content]]:
        if self.state == EdgeState.OFFLINE:
            return CacheStatus.BYPASS, None

        entry = self.cache.get(path)
        if entry is None:
            self.misses += 1
            return CacheStatus.MISS, None

        if not entry.is_fresh(now):
            self.stale += 1
            del self.cache[path]
            return CacheStatus.STALE, None

        self.cache.move_to_end(path)
        self.hits += 1
        return CacheStatus.HIT, entry.content

    def put(self, content: Content, now: float) -> None:
        if not content.cacheable or self.state == EdgeState.OFFLINE:
            return

        if content.path in self.cache:
            del self.cache[content.path]

        self.cache[content.path] = CacheEntry(content, now)
        self.cache.move_to_end(content.path)

        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
            self.evictions += 1

    def invalidate(self, path: str) -> bool:
        return self.cache.pop(path, None) is not None


@dataclass
class RequestResult:
    path: str
    edge_id: str
    status: CacheStatus
    latency_ms: int
    version: Optional[int]
    message: str


class OriginServer:
    def __init__(self) -> None:
        self._content: Dict[str, Content] = {}
        self.available = True

    def publish(
        self,
        path: str,
        body: str,
        content_type: str = "text/plain",
        cacheable: bool = True,
        ttl_seconds: int = 30,
    ) -> Content:
        if not path.startswith("/") or ".." in path:
            raise ValueError("Invalid content path")

        previous = self._content.get(path)
        version = 1 if previous is None else previous.version + 1

        content = Content(
            path=path,
            body=body,
            content_type=content_type,
            version=version,
            cacheable=cacheable,
            ttl_seconds=ttl_seconds,
        )
        self._content[path] = content
        return content

    def fetch(self, path: str) -> Content:
        if not self.available:
            raise ConnectionError("Origin server unavailable")

        if path not in self._content:
            raise FileNotFoundError(path)

        return self._content[path]


class CDN:
    def __init__(self, origin: OriginServer) -> None:
        self.origin = origin
        self.edges: Dict[str, EdgeServer] = {}
        self.region_distance: Dict[tuple[str, str], int] = {}
        self.requests = 0
        self.origin_fetches = 0
        self.invalid_requests = 0

    def add_edge(self, edge: EdgeServer) -> None:
        self.edges[edge.edge_id] = edge

    def set_distance(self, region_a: str, region_b: str, latency_ms: int) -> None:
        if latency_ms < 0:
            raise ValueError("Latency cannot be negative")
        self.region_distance[(region_a, region_b)] = latency_ms
        self.region_distance[(region_b, region_a)] = latency_ms

    def _distance(self, source: str, destination: str) -> int:
        if source == destination:
            return 0
        return self.region_distance.get((source, destination), 100)

    def choose_edge(self, client_region: str) -> EdgeServer:
        candidates = [
            edge
            for edge in self.edges.values()
            if edge.state != EdgeState.OFFLINE
        ]
        if not candidates:
            raise RuntimeError("No available edge servers")

        def score(edge: EdgeServer) -> tuple[int, int]:
            health_penalty = 1000 if edge.state == EdgeState.DEGRADED else 0
            return (
                self._distance(client_region, edge.region)
                + edge.latency_ms
                + health_penalty,
                len(edge.cache),
            )

        return min(candidates, key=score)

    def request(
        self,
        path: str,
        client_region: str,
        now: Optional[float] = None,
        authorization: Optional[str] = None,
    ) -> RequestResult:
        self.requests += 1
        now = time.time() if now is None else now

        # A CDN should reject malformed paths before touching its cache or origin.
        if (
            not path.startswith("/")
            or len(path) > 2048
            or ".." in path
            or "\x00" in path
        ):
            self.invalid_requests += 1
            return RequestResult(
                path, "none", CacheStatus.BYPASS, 0, None, "Rejected path"
            )

        # Private content is not cached in this simplified model.
        private = path.startswith("/private/")
        if private and authorization is None:
            return RequestResult(
                path, "none", CacheStatus.BYPASS, 0, None,
                "Authorization required"
            )

        try:
            edge = self.choose_edge(client_region)
        except RuntimeError as exc:
            return RequestResult(
                path, "none", CacheStatus.ORIGIN_ERROR, 0, None, str(exc)
            )

        if not private:
            status, cached = edge.get(path, now)
            if status == CacheStatus.HIT and cached is not None:
                latency = self._distance(client_region, edge.region) + edge.latency_ms
                return RequestResult(
                    path, edge.edge_id, status, latency, cached.version, "Served by edge"
                )
        else:
            status = CacheStatus.BYPASS

        try:
            content = self.origin.fetch(path)
            self.origin_fetches += 1
        except (ConnectionError, FileNotFoundError) as exc:
            return RequestResult(
                path,
                edge.edge_id,
                CacheStatus.ORIGIN_ERROR,
                self._distance(client_region, edge.region) + edge.latency_ms,
                None,
                str(exc),
            )

        if not private:
            edge.put(content, now)

        latency = (
            self._distance(client_region, edge.region)
            + edge.latency_ms
            + 80
        )

        return RequestResult(
            path,
            edge.edge_id,
            status if status != CacheStatus.BYPASS else CacheStatus.BYPASS,
            latency,
            content.version,
            "Fetched from origin",
        )

    def invalidate(self, path: str) -> int:
        count = 0
        for edge in self.edges.values():
            count += int(edge.invalidate(path))
        return count

    def metrics(self) -> dict:
        hits = sum(edge.hits for edge in self.edges.values())
        misses = sum(edge.misses for edge in self.edges.values())
        stale = sum(edge.stale for edge in self.edges.values())
        return {
            "requests": self.requests,
            "cache_hits": hits,
            "cache_misses": misses,
            "stale_entries": stale,
            "origin_fetches": self.origin_fetches,
            "invalid_requests": self.invalid_requests,
            "hit_ratio": round(hits / self.requests, 3) if self.requests else 0.0,
        }


def run_demo() -> None:
    origin = OriginServer()
    origin.publish(
        "/assets/app.js",
        "console.log('release-1');",
        "application/javascript",
        ttl_seconds=20,
    )
    origin.publish(
        "/images/logo.svg",
        "<svg>logo</svg>",
        "image/svg+xml",
        ttl_seconds=60,
    )
    origin.publish(
        "/private/report.json",
        '{"classification":"internal"}',
        "application/json",
        cacheable=False,
    )

    cdn = CDN(origin)
    cdn.add_edge(EdgeServer("edge-delhi", "DEL", capacity=2, latency_ms=8))
    cdn.add_edge(EdgeServer("edge-mumbai", "BOM", capacity=2, latency_ms=12))
    cdn.add_edge(EdgeServer("edge-london", "LON", capacity=2, latency_ms=18))
    cdn.add_edge(
        EdgeServer("edge-singapore", "SIN", capacity=2, latency_ms=10)
    )

    for a, b, latency in [
        ("DEL", "BOM", 18),
        ("DEL", "LON", 120),
        ("DEL", "SIN", 65),
        ("BOM", "LON", 130),
        ("BOM", "SIN", 55),
        ("SIN", "LON", 160),
    ]:
        cdn.set_distance(a, b, latency)

    t0 = 1_000.0

    requests = [
        ("/assets/app.js", "DEL", t0),
        ("/assets/app.js", "DEL", t0 + 2),
        ("/images/logo.svg", "SIN", t0 + 3),
        ("/images/logo.svg", "SIN", t0 + 4),
        ("/private/report.json", "DEL", t0 + 5),
    ]

    for path, region, timestamp in requests:
        auth = "Bearer internal-token" if path.startswith("/private/") else None
        result = cdn.request(path, region, timestamp, auth)
        print(
            f"{result.path:24} edge={result.edge_id:15} "
            f"status={result.status.value:12} latency={result.latency_ms:4}ms "
            f"version={result.version} message={result.message}"
        )

    # Simulate expiration and a new origin version.
    origin.publish(
        "/assets/app.js",
        "console.log('release-2');",
        "application/javascript",
        ttl_seconds=20,
    )

    stale_result = cdn.request("/assets/app.js", "DEL", t0 + 25)
    print(
        f"stale/refresh: {stale_result.status.value}, "
        f"version={stale_result.version}"
    )

    # Explicit invalidation is useful for urgent content changes.
    invalidated = cdn.invalidate("/images/logo.svg")
    print(f"invalidated edge entries: {invalidated}")

    # Demonstrate origin failure without crashing the CDN process.
    origin.available = False
    failure = cdn.request("/images/logo.svg", "BOM", t0 + 100)
    print(f"origin failure: {failure.status.value} - {failure.message}")

    print("metrics:", cdn.metrics())

    # Assertions provide lightweight executable verification.
    assert cdn.metrics()["requests"] == len(requests) + 2
    assert failure.status == CacheStatus.ORIGIN_ERROR
    assert stale_result.version == 2


if __name__ == "__main__":
    run_demo()
