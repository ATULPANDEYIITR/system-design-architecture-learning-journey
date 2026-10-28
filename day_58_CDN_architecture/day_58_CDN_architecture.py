#!/usr/bin/env python3
"""
CDN architecture simulation.

Models:
- Origin servers
- Edge locations
- Cache policies
- Cache-Control semantics
- TTL and stale entries
- Cache hits and misses
- Origin fetches
- Cache invalidation
- Revalidation
- LRU eviction
- Request routing to the nearest edge
- Basic cache-poisoning protections
- Metrics and reporting

The simulation is deterministic and uses only the Python standard library.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import re
from typing import Dict, Iterable, List, Optional, Tuple


class CacheStatus(Enum):
    HIT = "HIT"
    MISS = "MISS"
    REVALIDATED = "REVALIDATED"
    BYPASS = "BYPASS"
    STALE = "STALE"


class CacheMode(Enum):
    CACHEABLE = "cacheable"
    NO_STORE = "no-store"
    PRIVATE = "private"


@dataclass(frozen=True)
class CachePolicy:
    default_ttl_seconds: int = 60
    max_ttl_seconds: int = 3600
    min_ttl_seconds: int = 0
    cache_authenticated: bool = False
    respect_origin_no_store: bool = True
    query_allowlist: Tuple[str, ...] = ()
    ignore_tracking_parameters: bool = True

    def __post_init__(self) -> None:
        if self.default_ttl_seconds < 0:
            raise ValueError("default TTL cannot be negative")
        if self.max_ttl_seconds < self.default_ttl_seconds:
            raise ValueError("max TTL must be >= default TTL")
        if self.min_ttl_seconds < 0:
            raise ValueError("minimum TTL cannot be negative")


@dataclass
class Request:
    method: str
    host: str
    path: str
    query: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.method = self.method.upper()
        if self.method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"unsupported method: {self.method}")
        if not self.host or not re.fullmatch(r"[A-Za-z0-9.-]+", self.host):
            raise ValueError("invalid host")
        if not self.path.startswith("/"):
            raise ValueError("path must begin with '/'")


@dataclass
class OriginResponse:
    status: int
    body: str
    content_type: str
    etag: str
    cache_control: str
    generated_at: datetime

    @property
    def size(self) -> int:
        return len(self.body.encode("utf-8"))


@dataclass
class CacheEntry:
    key: str
    response: OriginResponse
    stored_at: datetime
    expires_at: datetime
    last_accessed: datetime

    @property
    def fresh(self) -> bool:
        return self.expires_at > self.last_accessed


@dataclass
class EdgeMetrics:
    requests: int = 0
    hits: int = 0
    misses: int = 0
    stale: int = 0
    bypasses: int = 0
    revalidations: int = 0
    origin_fetches: int = 0
    evictions: int = 0

    @property
    def hit_ratio(self) -> float:
        return self.hits / self.requests if self.requests else 0.0


class OriginServer:
    def __init__(self, name: str) -> None:
        self.name = name
        self._objects: Dict[str, OriginResponse] = {}
        self.fetch_count = 0

    def publish(
        self,
        path: str,
        body: str,
        content_type: str,
        cache_control: str = "public, max-age=60",
        now: Optional[datetime] = None,
    ) -> None:
        if not path.startswith("/"):
            raise ValueError("origin path must begin with '/'")
        now = now or datetime.now(timezone.utc)
        etag = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        self._objects[path] = OriginResponse(
            status=200,
            body=body,
            content_type=content_type,
            etag=etag,
            cache_control=cache_control,
            generated_at=now,
        )

    def fetch(
        self,
        path: str,
        if_none_match: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Tuple[OriginResponse, bool]:
        now = now or datetime.now(timezone.utc)
        self.fetch_count += 1

        response = self._objects.get(path)
        if response is None:
            return (
                OriginResponse(
                    status=404,
                    body="Not Found",
                    content_type="text/plain",
                    etag="404",
                    cache_control="no-store",
                    generated_at=now,
                ),
                False,
            )

        if if_none_match and if_none_match == response.etag:
            return response, True

        return response, False


class EdgeLocation:
    def __init__(self, name: str, capacity: int, policy: CachePolicy) -> None:
        if capacity <= 0:
            raise ValueError("edge capacity must be positive")
        self.name = name
        self.capacity = capacity
        self.policy = policy
        self.cache: "OrderedDict[str, CacheEntry]" = OrderedDict()
        self.metrics = EdgeMetrics()

    def _parse_max_age(self, cache_control: str) -> Optional[int]:
        match = re.search(r"(?:^|,\s*)max-age=(\d+)", cache_control)
        return int(match.group(1)) if match else None

    def _cache_mode(self, response: OriginResponse) -> CacheMode:
        directives = {
            item.strip().lower()
            for item in response.cache_control.split(",")
            if item.strip()
        }

        if "no-store" in directives and self.policy.respect_origin_no_store:
            return CacheMode.NO_STORE

        if "private" in directives:
            return CacheMode.PRIVATE

        return CacheMode.CACHEABLE

    def _ttl(self, response: OriginResponse) -> int:
        origin_ttl = self._parse_max_age(response.cache_control)
        if origin_ttl is None:
            origin_ttl = self.policy.default_ttl_seconds

        return max(
            self.policy.min_ttl_seconds,
            min(origin_ttl, self.policy.max_ttl_seconds),
        )

    def get(self, key: str, now: datetime) -> Optional[CacheEntry]:
        entry = self.cache.get(key)
        if entry is None:
            return None

        entry.last_accessed = now
        self.cache.move_to_end(key)
        return entry

    def put(self, key: str, response: OriginResponse, now: datetime) -> bool:
        if self._cache_mode(response) != CacheMode.CACHEABLE:
            return False

        ttl = self._ttl(response)
        entry = CacheEntry(
            key=key,
            response=response,
            stored_at=now,
            expires_at=now + timedelta(seconds=ttl),
            last_accessed=now,
        )

        if key in self.cache:
            del self.cache[key]

        self.cache[key] = entry

        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
            self.metrics.evictions += 1

        return True

    def invalidate(self, key: Optional[str] = None) -> int:
        if key is None:
            count = len(self.cache)
            self.cache.clear()
            return count

        return 1 if self.cache.pop(key, None) is not None else 0


class CDN:
    TRACKING_PARAMETERS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
    }

    def __init__(
        self,
        origin: OriginServer,
        edges: Iterable[EdgeLocation],
    ) -> None:
        self.origin = origin
        self.edges = list(edges)
        if not self.edges:
            raise ValueError("CDN requires at least one edge")
        self.total_requests = 0

    def _canonical_key(
        self,
        request: Request,
        policy: CachePolicy,
    ) -> str:
        pairs = []
        for name, value in request.query.items():
            if (
                policy.ignore_tracking_parameters
                and name.lower() in self.TRACKING_PARAMETERS
            ):
                continue
            if policy.query_allowlist and name not in policy.query_allowlist:
                continue
            pairs.append((name, value))

        pairs.sort()
        query = "&".join(f"{name}={value}" for name, value in pairs)

        return f"{request.host.lower()}|{request.method}|{request.path}|{query}"

    def route(self, client_region: str) -> EdgeLocation:
        # A production CDN would use latency, health, Anycast, or DNS
        # measurements. The simulation uses a deterministic region map.
        region = client_region.lower()
        preferred = {
            "india": ["blr", "bom", "del"],
            "asia": ["sin", "bom", "tok"],
            "europe": ["fra", "lon", "ams"],
            "north-america": ["iad", "dfw", "sfo"],
        }

        candidates = preferred.get(region, [])
        for candidate in candidates:
            for edge in self.edges:
                if edge.name.lower() == candidate:
                    return edge

        return self.edges[0]

    def request(
        self,
        request: Request,
        client_region: str,
        now: datetime,
    ) -> Tuple[OriginResponse, CacheStatus, str]:
        self.total_requests += 1
        edge = self.route(client_region)
        edge.metrics.requests += 1

        if request.method not in {"GET", "HEAD"}:
            edge.metrics.bypasses += 1
            response, _ = self.origin.fetch(request.path, now=now)
            return response, CacheStatus.BYPASS, edge.name

        if "Authorization" in request.headers and not edge.policy.cache_authenticated:
            edge.metrics.bypasses += 1
            response, _ = self.origin.fetch(request.path, now=now)
            return response, CacheStatus.BYPASS, edge.name

        key = self._canonical_key(request, edge.policy)
        entry = edge.get(key, now)

        if entry is not None:
            if entry.expires_at > now:
                edge.metrics.hits += 1
                return entry.response, CacheStatus.HIT, edge.name

            edge.metrics.stale += 1

            response, not_modified = self.origin.fetch(
                request.path,
                if_none_match=entry.response.etag,
                now=now,
            )
            edge.metrics.origin_fetches += 1

            if not_modified:
                entry.stored_at = now
                entry.expires_at = now + timedelta(
                    seconds=edge._ttl(entry.response)
                )
                entry.last_accessed = now
                edge.metrics.revalidations += 1
                return entry.response, CacheStatus.REVALIDATED, edge.name

            edge.put(key, response, now)
            edge.metrics.misses += 1
            return response, CacheStatus.STALE, edge.name

        response, _ = self.origin.fetch(request.path, now=now)
        edge.metrics.origin_fetches += 1
        edge.metrics.misses += 1
        edge.put(key, response, now)

        return response, CacheStatus.MISS, edge.name

    def purge(self, path: Optional[str] = None) -> int:
        if path is None:
            return sum(edge.invalidate() for edge in self.edges)

        total = 0
        for edge in self.edges:
            keys = [
                key
                for key in edge.cache
                if f"|{path}|" in key
            ]
            for key in keys:
                total += edge.invalidate(key)
        return total

    def report(self) -> List[dict]:
        return [
            {
                "edge": edge.name,
                "requests": edge.metrics.requests,
                "hits": edge.metrics.hits,
                "misses": edge.metrics.misses,
                "stale": edge.metrics.stale,
                "bypasses": edge.metrics.bypasses,
                "revalidations": edge.metrics.revalidations,
                "origin_fetches": edge.metrics.origin_fetches,
                "evictions": edge.metrics.evictions,
                "hit_ratio": round(edge.metrics.hit_ratio, 3),
                "cached_objects": len(edge.cache),
            }
            for edge in self.edges
        ]


def run_demo() -> None:
    start = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)

    policy = CachePolicy(
        default_ttl_seconds=30,
        max_ttl_seconds=300,
        query_allowlist=("version", "lang"),
        cache_authenticated=False,
    )

    origin = OriginServer("origin-primary")
    origin.publish(
        "/assets/app.js",
        "console.log('release-42');",
        "application/javascript",
        "public, max-age=120",
        start,
    )
    origin.publish(
        "/index.html",
        "<html><body>Release 42</body></html>",
        "text/html",
        "public, max-age=20",
        start,
    )
    origin.publish(
        "/account",
        "private account response",
        "text/plain",
        "private, max-age=30",
        start,
    )

    edges = [
        EdgeLocation("blr", 2, policy),
        EdgeLocation("fra", 2, policy),
        EdgeLocation("iad", 2, policy),
    ]

    cdn = CDN(origin, edges)

    requests = [
        (
            Request("GET", "example.test", "/assets/app.js"),
            "india",
            start,
        ),
        (
            Request("GET", "example.test", "/assets/app.js"),
            "india",
            start + timedelta(seconds=10),
        ),
        (
            Request(
                "GET",
                "example.test",
                "/assets/app.js",
                {"utm_source": "newsletter"},
            ),
            "india",
            start + timedelta(seconds=15),
        ),
        (
            Request("GET", "example.test", "/index.html"),
            "europe",
            start + timedelta(seconds=5),
        ),
        (
            Request("GET", "example.test", "/index.html"),
            "europe",
            start + timedelta(seconds=30),
        ),
        (
            Request(
                "GET",
                "example.test",
                "/account",
                headers={"Authorization": "Bearer secret"},
            ),
            "india",
            start + timedelta(seconds=20),
        ),
        (
            Request("POST", "example.test", "/account"),
            "india",
            start + timedelta(seconds=25),
        ),
    ]

    for request, region, timestamp in requests:
        response, status, edge = cdn.request(request, region, timestamp)
        print(
            f"{timestamp.isoformat()} "
            f"{request.method} {request.path} "
            f"edge={edge} status={status.value} "
            f"http={response.status}"
        )

    print("\nOrigin fetches:", origin.fetch_count)
    print("Cache report:")
    for row in cdn.report():
        print(row)

    purged = cdn.purge("/assets/app.js")
    print(f"\nPurged asset entries: {purged}")

    response, status, edge = cdn.request(
        Request("GET", "example.test", "/assets/app.js"),
        "india",
        start + timedelta(seconds=40),
    )
    print(
        f"Post-purge request: edge={edge}, "
        f"status={status.value}, http={response.status}"
    )

    assert origin.fetch_count >= 1
    assert response.status == 200
    assert all(edge.capacity >= len(edge.cache) for edge in edges)


if __name__ == "__main__":
    run_demo()
