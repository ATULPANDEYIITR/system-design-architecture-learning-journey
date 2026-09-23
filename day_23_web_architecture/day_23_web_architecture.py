"""
Web Architecture, Client-Server Architecture, and the Browser
Request-Response Lifecycle
===============================================================

A self-contained study program that demonstrates how a web application
works from browser input through HTTP requests, server routing,
application processing, response generation, caching, cookies,
sessions, authentication, validation, errors, concurrency, and
basic production-oriented considerations.

The program intentionally uses only Python's standard library.

Run:
    python web_architecture.py

The demonstrations are local. No external Internet connection is required.
"""

from __future__ import annotations

import hashlib
import http.client
import http.server
import json
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================================
# 1. FUNDAMENTAL WEB ARCHITECTURE
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_architecture() -> None:
    section("1. Web architecture fundamentals")

    architecture = {
        "client": "Usually a browser or mobile application. It initiates requests.",
        "server": "Receives requests, executes application logic, and returns responses.",
        "HTTP": "Application-layer protocol commonly used for browser-server communication.",
        "URL": "Identifies a resource or endpoint, including scheme, host, path, and query.",
        "request": "Client-to-server message containing method, target, headers, and optionally a body.",
        "response": "Server-to-client message containing status, headers, and optionally a body.",
        "DNS": "Translates a domain name into an IP address before a connection is established.",
        "TCP/TLS": "Provides reliable transport and, for HTTPS, encrypted communication.",
    }

    for name, definition in architecture.items():
        print(f"{name.upper():12} -> {definition}")

    print(
        "\nTypical high-level sequence:\n"
        "Browser -> DNS -> TCP/TLS -> HTTP request -> Web server -> "
        "Application -> Database/other services -> HTTP response -> Browser"
    )


# ============================================================================
# 2. URL STRUCTURE
# ============================================================================

@dataclass
class ParsedURL:
    scheme: str
    hostname: str
    port: Optional[int]
    path: str
    query: Dict[str, List[str]]
    fragment: str


def parse_url(url: str) -> ParsedURL:
    """Parse a URL into its major architectural components."""
    parsed = urllib.parse.urlsplit(url)

    if not parsed.scheme:
        raise ValueError("URL must contain a scheme such as http or https.")
    if not parsed.hostname:
        raise ValueError("URL must contain a hostname.")

    return ParsedURL(
        scheme=parsed.scheme,
        hostname=parsed.hostname,
        port=parsed.port,
        path=parsed.path or "/",
        query=urllib.parse.parse_qs(parsed.query),
        fragment=parsed.fragment,
    )


def demonstrate_url() -> None:
    section("2. URL anatomy")

    url = "https://example.com:443/products?id=42&category=books#details"
    parsed = parse_url(url)

    print(f"Original URL : {url}")
    print(f"Scheme       : {parsed.scheme}")
    print(f"Hostname     : {parsed.hostname}")
    print(f"Port         : {parsed.port}")
    print(f"Path         : {parsed.path}")
    print(f"Query        : {parsed.query}")
    print(f"Fragment     : {parsed.fragment}")

    print(
        "\nImportant distinction: the URL fragment (#details) is normally "
        "handled by the browser and is not sent to the server as part of "
        "the HTTP request target."
    )


# ============================================================================
# 3. HTTP REQUEST AND RESPONSE MODELS
# ============================================================================

@dataclass
class HTTPRequest:
    method: str
    target: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""

    def display(self) -> None:
        print(f"{self.method} {self.target} HTTP/1.1")
        for name, value in self.headers.items():
            print(f"{name}: {value}")
        print()
        if self.body:
            print(self.body)


@dataclass
class HTTPResponse:
    status_code: int
    reason: str
    headers: Dict[str, str] = field(default_factory=dict)
    body: str = ""

    def display(self) -> None:
        print(f"HTTP/1.1 {self.status_code} {self.reason}")
        for name, value in self.headers.items():
            print(f"{name}: {value}")
        print()
        if self.body:
            print(self.body)


def demonstrate_http_messages() -> None:
    section("3. HTTP request and response messages")

    request = HTTPRequest(
        method="GET",
        target="/products?id=42",
        headers={
            "Host": "shop.example",
            "Accept": "application/json",
            "User-Agent": "StudyBrowser/1.0",
        },
    )

    response = HTTPResponse(
        status_code=200,
        reason="OK",
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "max-age=60",
        },
        body='{"id":42,"name":"Example Product"}',
    )

    print("REQUEST")
    request.display()
    print("RESPONSE")
    response.display()


# ============================================================================
# 4. HTTP METHODS
# ============================================================================

class HTTPMethodDemo:
    """Demonstrates the semantic purpose of common HTTP methods."""

    METHODS = {
        "GET": "Retrieve a representation. It should not intentionally modify server state.",
        "POST": "Submit data, commonly to create a resource or trigger processing.",
        "PUT": "Create or replace a resource at a known target URI.",
        "PATCH": "Partially modify an existing resource.",
        "DELETE": "Request removal of a resource.",
        "HEAD": "Like GET for headers, normally without a response body.",
        "OPTIONS": "Ask what communication options are supported.",
    }

    @classmethod
    def show(cls) -> None:
        section("4. HTTP methods")
        for method, meaning in cls.METHODS.items():
            print(f"{method:8} {meaning}")


# ============================================================================
# 5. STATUS CODES
# ============================================================================

def explain_status_codes() -> None:
    section("5. HTTP status codes")

    groups = {
        "1xx": "Informational",
        "2xx": "Successful",
        "3xx": "Redirection",
        "4xx": "Client-side request problem",
        "5xx": "Server-side processing problem",
    }

    for group, meaning in groups.items():
        print(f"{group}: {meaning}")

    examples = {
        200: "OK",
        201: "Created",
        204: "No Content",
        301: "Moved Permanently",
        302: "Found",
        304: "Not Modified",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Content",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    print("\nCommon codes:")
    for code, meaning in examples.items():
        print(f"{code}: {meaning}")


# ============================================================================
# 6. ROUTING AND APPLICATION PROCESSING
# ============================================================================

@dataclass
class Route:
    method: str
    path: str
    handler: Callable[[HTTPRequest], HTTPResponse]


class MiniApplication:
    """A small educational HTTP application/router."""

    def __init__(self) -> None:
        self.routes: List[Route] = []

    def route(
        self,
        method: str,
        path: str,
        handler: Callable[[HTTPRequest], HTTPResponse],
    ) -> None:
        self.routes.append(Route(method.upper(), path, handler))

    def handle(self, request: HTTPRequest) -> HTTPResponse:
        parsed = urllib.parse.urlsplit(request.target)
        path = parsed.path or "/"

        for route in self.routes:
            if route.method == request.method.upper() and route.path == path:
                return route.handler(request)

        return HTTPResponse(
            status_code=404,
            reason="Not Found",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"error": "Route not found"}),
        )


def home_handler(request: HTTPRequest) -> HTTPResponse:
    return HTTPResponse(
        status_code=200,
        reason="OK",
        headers={"Content-Type": "text/html; charset=utf-8"},
        body="<html><body><h1>Home</h1></body></html>",
    )


def health_handler(request: HTTPRequest) -> HTTPResponse:
    return HTTPResponse(
        status_code=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"status": "healthy"}),
    )


def demonstrate_routing() -> None:
    section("6. Server routing")

    application = MiniApplication()
    application.route("GET", "/", home_handler)
    application.route("GET", "/health", health_handler)

    requests = [
        HTTPRequest("GET", "/"),
        HTTPRequest("GET", "/health"),
        HTTPRequest("GET", "/missing"),
    ]

    for request in requests:
        response = application.handle(request)
        print(
            f"{request.method} {request.target} "
            f"-> {response.status_code} {response.reason}"
        )


# ============================================================================
# 7. QUERY PARAMETERS AND JSON
# ============================================================================

def search_handler(request: HTTPRequest) -> HTTPResponse:
    parsed = urllib.parse.urlsplit(request.target)
    parameters = urllib.parse.parse_qs(parsed.query)

    term = parameters.get("q", [""])[0].strip()

    if not term:
        return HTTPResponse(
            status_code=400,
            reason="Bad Request",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"error": "q is required"}),
        )

    results = [
        {"id": 1, "title": f"Result containing {term}"},
        {"id": 2, "title": f"Another result for {term}"},
    ]

    return HTTPResponse(
        status_code=200,
        reason="OK",
        headers={"Content-Type": "application/json"},
        body=json.dumps({"query": term, "results": results}),
    )


def demonstrate_query_parameters() -> None:
    section("7. Query parameters and structured responses")

    for target in ["/search?q=browser", "/search", "/search?q="]:
        response = search_handler(HTTPRequest("GET", target))
        print(f"{target}")
        print(f"Status: {response.status_code}")
        print(f"Body: {response.body}\n")


# ============================================================================
# 8. POST REQUESTS, JSON VALIDATION, AND ERROR HANDLING
# ============================================================================

def create_user_handler(request: HTTPRequest) -> HTTPResponse:
    content_type = request.headers.get("Content-Type", "").lower()

    if "application/json" not in content_type:
        return HTTPResponse(
            415,
            "Unsupported Media Type",
            {"Content-Type": "application/json"},
            json.dumps({"error": "Expected application/json"}),
        )

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HTTPResponse(
            400,
            "Bad Request",
            {"Content-Type": "application/json"},
            json.dumps({"error": "Invalid JSON"}),
        )

    if not isinstance(payload, dict):
        return HTTPResponse(
            422,
            "Unprocessable Content",
            {"Content-Type": "application/json"},
            json.dumps({"error": "JSON object required"}),
        )

    name = payload.get("name")
    email = payload.get("email")

    if not isinstance(name, str) or not name.strip():
        return HTTPResponse(
            422,
            "Unprocessable Content",
            {"Content-Type": "application/json"},
            json.dumps({"error": "name must be a non-empty string"}),
        )

    if not isinstance(email, str) or "@" not in email:
        return HTTPResponse(
            422,
            "Unprocessable Content",
            {"Content-Type": "application/json"},
            json.dumps({"error": "email is invalid"}),
        )

    user = {
        "id": secrets.randbelow(900000) + 100000,
        "name": name.strip(),
        "email": email.strip().lower(),
    }

    return HTTPResponse(
        201,
        "Created",
        {
            "Content-Type": "application/json",
            "Location": f"/users/{user['id']}",
        },
        json.dumps(user),
    )


def demonstrate_post_validation() -> None:
    section("8. POST, JSON, validation, and errors")

    examples = [
        ("application/json", '{"name":"Atul","email":"atul@example.com"}'),
        ("application/json", '{"name":"","email":"bad"}'),
        ("application/json", '{"name":"Atul"'),
        ("text/plain", "hello"),
    ]

    for content_type, body in examples:
        request = HTTPRequest(
            "POST",
            "/users",
            {"Content-Type": content_type},
            body,
        )
        response = create_user_handler(request)
        print(f"Input: {body}")
        print(f"Result: {response.status_code} {response.reason}")
        print(f"Body: {response.body}\n")


# ============================================================================
# 9. COOKIES AND SESSIONS
# ============================================================================

class SessionStore:
    """Very small in-memory session store for demonstration purposes."""

    def __init__(self) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create(self, user_id: int) -> str:
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            "user_id": user_id,
            "created_at": time.time(),
        }
        return session_id

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


def demonstrate_sessions() -> None:
    section("9. Cookies and sessions")

    store = SessionStore()
    session_id = store.create(user_id=42)

    print(f"Generated session identifier: {session_id}")
    print(f"Stored server-side session: {store.get(session_id)}")

    cookie_header = (
        f"session_id={session_id}; "
        "Path=/; HttpOnly; Secure; SameSite=Lax"
    )

    print(f"Example Set-Cookie header: {cookie_header}")

    print(
        "\nA cookie usually carries an identifier. The server can use that "
        "identifier to locate session state. HttpOnly reduces JavaScript "
        "access to the cookie, Secure restricts transmission to HTTPS, and "
        "SameSite influences cross-site cookie behavior."
    )


# ============================================================================
# 10. AUTHENTICATION AND PASSWORD STORAGE
# ============================================================================

def password_digest(password: str, salt: bytes) -> str:
    """
    Educational password derivation example.

    Production systems should normally use a password-specific password
    hashing function such as Argon2id, bcrypt, or scrypt rather than a
    general-purpose hash directly.
    """
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000,
    )
    return derived.hex()


def demonstrate_password_storage() -> None:
    section("10. Authentication fundamentals")

    password = "example-password"
    salt = secrets.token_bytes(16)
    digest = password_digest(password, salt)

    print(f"Salt length: {len(salt)} bytes")
    print(f"Derived value: {digest[:40]}...")
    print(
        "\nThe server should not store ordinary passwords in plaintext. "
        "Password verification derives a value from the submitted password "
        "and compares it with the stored representation."
    )


# ============================================================================
# 11. CACHE MODEL
# ============================================================================

@dataclass
class CacheEntry:
    value: HTTPResponse
    expires_at: float


class SimpleCache:
    def __init__(self) -> None:
        self.entries: Dict[str, CacheEntry] = {}

    def put(self, key: str, response: HTTPResponse, ttl: float) -> None:
        self.entries[key] = CacheEntry(response, time.time() + ttl)

    def get(self, key: str) -> Optional[HTTPResponse]:
        entry = self.entries.get(key)

        if entry is None:
            return None

        if time.time() >= entry.expires_at:
            del self.entries[key]
            return None

        return entry.value


def demonstrate_cache() -> None:
    section("11. HTTP caching")

    cache = SimpleCache()

    response = HTTPResponse(
        200,
        "OK",
        {"Cache-Control": "max-age=10"},
        '{"message":"cached"}',
    )

    cache.put("/data", response, ttl=2)

    print("First lookup:", cache.get("/data").body)
    time.sleep(0.05)
    print("Second lookup:", cache.get("/data").body)

    print(
        "\nReal systems may use browser caches, shared proxy caches, "
        "CDNs, ETags, Last-Modified, Cache-Control, and conditional requests."
    )


# ============================================================================
# 12. CONDITIONAL REQUESTS AND ETAG
# ============================================================================

def calculate_etag(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def conditional_resource(
    request: HTTPRequest,
    content: str,
) -> HTTPResponse:
    etag = calculate_etag(content)

    if request.headers.get("If-None-Match") == etag:
        return HTTPResponse(
            304,
            "Not Modified",
            {"ETag": etag},
            "",
        )

    return HTTPResponse(
        200,
        "OK",
        {
            "Content-Type": "text/plain",
            "ETag": etag,
            "Cache-Control": "max-age=60",
        },
        content,
    )


def demonstrate_etag() -> None:
    section("12. Conditional requests")

    first = conditional_resource(
        HTTPRequest("GET", "/document"),
        "Version 1 of the document",
    )

    print(f"Initial request: {first.status_code}")
    print(f"ETag: {first.headers['ETag']}")

    second = conditional_resource(
        HTTPRequest(
            "GET",
            "/document",
            {"If-None-Match": first.headers["ETag"]},
        ),
        "Version 1 of the document",
    )

    print(f"Conditional request: {second.status_code}")
    print("An unchanged representation can therefore avoid transferring the body.")


# ============================================================================
# 13. MIDDLEWARE
# ============================================================================

Middleware = Callable[
    [HTTPRequest, Callable[[HTTPRequest], HTTPResponse]],
    HTTPResponse,
]


def logging_middleware(
    request: HTTPRequest,
    next_handler: Callable[[HTTPRequest], HTTPResponse],
) -> HTTPResponse:
    start = time.perf_counter()
    response = next_handler(request)
    elapsed = (time.perf_counter() - start) * 1000
    print(
        f"[middleware] {request.method} {request.target} "
        f"-> {response.status_code} in {elapsed:.3f} ms"
    )
    return response


def security_headers_middleware(
    request: HTTPRequest,
    next_handler: Callable[[HTTPRequest], HTTPResponse],
) -> HTTPResponse:
    response = next_handler(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


def compose_middleware(
    handler: Callable[[HTTPRequest], HTTPResponse],
    middleware: List[Middleware],
) -> Callable[[HTTPRequest], HTTPResponse]:
    current = handler

    for item in reversed(middleware):
        previous = current

        def wrapped(
            request: HTTPRequest,
            item: Middleware = item,
            previous: Callable[[HTTPRequest], HTTPResponse] = previous,
        ) -> HTTPResponse:
            return item(request, previous)

        current = wrapped

    return current


def demonstrate_middleware() -> None:
    section("13. Middleware")

    def handler(request: HTTPRequest) -> HTTPResponse:
        return HTTPResponse(
            200,
            "OK",
            {"Content-Type": "text/plain"},
            "Middleware demonstration",
        )

    application = compose_middleware(
        handler,
        [logging_middleware, security_headers_middleware],
    )

    response = application(HTTPRequest("GET", "/middleware"))
    print(response.headers)


# ============================================================================
# 14. CORS
# ============================================================================

def demonstrate_cors() -> None:
    section("14. Cross-Origin Resource Sharing")

    print(
        "Origin is defined by scheme + host + port."
    )
    print(
        "Example A: https://app.example.com"
        "\nExample B: https://api.example.com"
        "\nThese are different origins because their hosts differ."
    )

    response_headers = {
        "Access-Control-Allow-Origin": "https://app.example.com",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    for name, value in response_headers.items():
        print(f"{name}: {value}")

    print(
        "\nCORS is enforced by browsers. It is not an authentication mechanism."
    )


# ============================================================================
# 15. REQUEST LIFECYCLE SIMULATION
# ============================================================================

@dataclass
class LifecycleEvent:
    stage: str
    description: str
    approximate_ms: float


def simulate_request_lifecycle() -> List[LifecycleEvent]:
    events: List[LifecycleEvent] = []

    stages = [
        ("Browser", "User enters a URL or activates a link.", 0.1),
        ("DNS", "Domain name is resolved to an IP address.", 3.2),
        ("TCP", "A transport connection is established.", 4.8),
        ("TLS", "HTTPS negotiates encryption and server identity.", 12.5),
        ("HTTP request", "Browser sends method, target, headers, and optional body.", 0.3),
        ("Web server", "Connection is accepted and request is routed.", 1.2),
        ("Application", "Business logic validates and processes the request.", 5.7),
        ("Database", "Application retrieves or changes persistent data.", 8.4),
        ("HTTP response", "Status, headers, and body are returned.", 0.8),
        ("Browser", "Response is parsed and resources are processed.", 6.1),
        ("Rendering", "DOM, CSSOM, layout, painting, and compositing occur.", 9.3),
    ]

    elapsed = 0.0
    for stage, description, duration in stages:
        elapsed += duration
        events.append(LifecycleEvent(stage, description, elapsed))

    return events


def demonstrate_lifecycle() -> None:
    section("15. Browser request-response lifecycle")

    for event in simulate_request_lifecycle():
        print(
            f"{event.approximate_ms:6.1f} ms | "
            f"{event.stage:16} | {event.description}"
        )

    print(
        "\nThe numbers are illustrative rather than measurements. "
        "Actual latency depends on network distance, DNS caching, TLS reuse, "
        "server load, database latency, browser cache state, and many other factors."
    )


# ============================================================================
# 16. REAL LOCAL HTTP SERVER
# ============================================================================

class StudyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    A real HTTP/1.x server handler using Python's standard library.

    This demonstrates the point at which a browser request becomes an
    application-level handler invocation.
    """

    server_version = "WebArchitectureStudy/1.0"

    def send_json(
        self,
        status: int,
        payload: Dict[str, Any],
    ) -> None:
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path == "/":
            self.send_json(
                200,
                {
                    "message": "Local web server is running",
                    "method": self.command,
                    "path": parsed.path,
                },
            )
            return

        if parsed.path == "/hello":
            parameters = urllib.parse.parse_qs(parsed.query)
            name = parameters.get("name", ["browser"])[0]

            self.send_json(
                200,
                {
                    "message": f"Hello, {name}",
                    "query": parameters,
                },
            )
            return

        if parsed.path == "/status":
            self.send_json(
                200,
                {
                    "status": "healthy",
                    "server_time": time.time(),
                },
            )
            return

        self.send_json(
            404,
            {
                "error": "Resource not found",
                "path": parsed.path,
            },
        )

    def do_POST(self) -> None:
        if self.path != "/echo":
            self.send_json(404, {"error": "Resource not found"})
            return

        content_length = self.headers.get("Content-Length")

        try:
            length = int(content_length or "0")
        except ValueError:
            self.send_json(400, {"error": "Invalid Content-Length"})
            return

        if length > 1_000_000:
            self.send_json(413, {"error": "Request body too large"})
            return

        raw_body = self.rfile.read(length)

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Expected valid UTF-8 JSON"})
            return

        self.send_json(
            200,
            {
                "received": body,
                "content_type": self.headers.get("Content-Type"),
            },
        )

    def log_message(self, format_string: str, *args: Any) -> None:
        print("[server]", format_string % args)


def run_real_http_server_demo() -> None:
    section("16. Real local HTTP request-response demonstration")

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        StudyHTTPRequestHandler,
    )

    host, port = server.server_address

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    print(f"Server listening at http://{host}:{port}")

    try:
        connection = http.client.HTTPConnection(host, port, timeout=5)

        print("\nGET /hello?name=Atul")
        connection.request(
            "GET",
            "/hello?name=Atul",
            headers={"Accept": "application/json"},
        )
        response = connection.getresponse()

        body = response.read().decode("utf-8")
        print(f"Status: {response.status} {response.reason}")
        print(f"Body: {body}")

        print("\nPOST /echo")
        payload = json.dumps({"topic": "web architecture"})
        connection.request(
            "POST",
            "/echo",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(payload.encode("utf-8"))),
            },
        )
        response = connection.getresponse()
        print(f"Status: {response.status} {response.reason}")
        print(f"Body: {response.read().decode('utf-8')}")

        connection.close()

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(
        "\nThis demonstration contains the actual request boundary: "
        "an HTTP client opens a connection, sends an HTTP request, "
        "the server parses it, application code executes, and an HTTP response returns."
    )


# ============================================================================
# 17. CONCURRENCY
# ============================================================================

def simulate_concurrent_requests() -> None:
    section("17. Concurrency and multiple clients")

    results: List[str] = []
    lock = threading.Lock()

    def process_request(request_id: int) -> None:
        start = time.perf_counter()
        time.sleep(0.03)
        elapsed = (time.perf_counter() - start) * 1000

        with lock:
            results.append(
                f"Request {request_id} completed in {elapsed:.2f} ms"
            )

    threads = [
        threading.Thread(target=process_request, args=(request_id,))
        for request_id in range(1, 6)
    ]

    start = time.perf_counter()

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    total = (time.perf_counter() - start) * 1000

    for result in sorted(results):
        print(result)

    print(f"Wall-clock time for five concurrent tasks: {total:.2f} ms")

    print(
        "\nConcurrency allows multiple requests to make progress without "
        "forcing every request to wait for unrelated work to finish."
    )


# ============================================================================
# 18. PERFORMANCE AND COMPLEXITY
# ============================================================================

def benchmark_lookup() -> None:
    section("18. Performance: data structure choice")

    values = list(range(100_000))
    value_set = set(values)

    target = 99_999

    start = time.perf_counter()
    target in values
    list_time = time.perf_counter() - start

    start = time.perf_counter()
    target in value_set
    set_time = time.perf_counter() - start

    print(f"List membership: {list_time * 1_000_000:.2f} microseconds")
    print(f"Set membership : {set_time * 1_000_000:.2f} microseconds")

    print(
        "\nList membership is O(n) in the average general case for a search "
        "through arbitrary values. Hash-set membership is approximately O(1) "
        "on average, subject to hashing and collision behavior."
    )


# ============================================================================
# 19. SECURITY CHECKS
# ============================================================================

def validate_path_component(value: str) -> bool:
    """
    Reject path traversal markers in a simple educational example.

    Real applications should use safe path APIs and authorization checks,
    not rely on a single string test.
    """
    decoded = urllib.parse.unquote(value)
    normalized = decoded.replace("\\", "/")

    return ".." not in normalized.split("/")


def demonstrate_security() -> None:
    section("19. Web security considerations")

    examples = [
        "images/profile.png",
        "../secrets.txt",
        "%2e%2e%2fsecrets.txt",
        "safe/file.txt",
    ]

    for value in examples:
        print(f"{value:30} -> allowed={validate_path_component(value)}")

    security_principles = [
        "Validate untrusted input on the server.",
        "Authenticate users before protected operations.",
        "Authorize every protected resource according to server-side rules.",
        "Use HTTPS for sensitive communication.",
        "Use parameterized database queries.",
        "Protect state-changing browser requests against CSRF where applicable.",
        "Encode output appropriately to reduce XSS risk.",
        "Limit request sizes and expensive operations.",
        "Do not expose internal stack traces to ordinary clients.",
        "Log security-relevant events without logging secrets.",
    ]

    print("\nImportant security principles:")
    for item in security_principles:
        print(f"- {item}")


# ============================================================================
# 20. PRODUCTION ARCHITECTURE
# ============================================================================

def demonstrate_production_architecture() -> None:
    section("20. From a simple server to production architecture")

    layers = [
        "Browser",
        "DNS",
        "CDN / edge cache",
        "Load balancer / reverse proxy",
        "Application servers",
        "Authentication / authorization",
        "Application services",
        "Cache",
        "Database",
        "Message queue / background workers",
        "Object storage",
        "Monitoring / logging / tracing",
    ]

    for index, layer in enumerate(layers, start=1):
        print(f"{index:02}. {layer}")

    print(
        "\nA production system may distribute these responsibilities across "
        "multiple machines or managed services. The request-response model "
        "remains the conceptual foundation even when the internal architecture "
        "becomes distributed."
    )


# ============================================================================
# 21. END-TO-END CASE STUDY
# ============================================================================

@dataclass
class Product:
    product_id: int
    name: str
    price: float
    stock: int


class ProductService:
    """Simple application service representing business logic."""

    def __init__(self) -> None:
        self.products = {
            1: Product(1, "Keyboard", 2499.0, 20),
            2: Product(2, "Monitor", 15999.0, 8),
            3: Product(3, "Mouse", 999.0, 50),
        }

    def get_product(self, product_id: int) -> Optional[Product]:
        return self.products.get(product_id)

    def reserve_stock(self, product_id: int, quantity: int) -> bool:
        product = self.get_product(product_id)

        if product is None or quantity <= 0:
            return False

        if product.stock < quantity:
            return False

        product.stock -= quantity
        return True


def product_handler(
    request: HTTPRequest,
    service: ProductService,
) -> HTTPResponse:
    parsed = urllib.parse.urlsplit(request.target)
    path_parts = parsed.path.strip("/").split("/")

    if len(path_parts) != 2 or path_parts[0] != "products":
        return HTTPResponse(
            404,
            "Not Found",
            {"Content-Type": "application/json"},
            json.dumps({"error": "Invalid product route"}),
        )

    try:
        product_id = int(path_parts[1])
    except ValueError:
        return HTTPResponse(
            400,
            "Bad Request",
            {"Content-Type": "application/json"},
            json.dumps({"error": "Product ID must be numeric"}),
        )

    product = service.get_product(product_id)

    if product is None:
        return HTTPResponse(
            404,
            "Not Found",
            {"Content-Type": "application/json"},
            json.dumps({"error": "Product not found"}),
        )

    return HTTPResponse(
        200,
        "OK",
        {"Content-Type": "application/json"},
        json.dumps(
            {
                "id": product.product_id,
                "name": product.name,
                "price": product.price,
                "stock": product.stock,
            }
        ),
    )


def demonstrate_end_to_end_case_study() -> None:
    section("21. End-to-end application case study")

    service = ProductService()

    requests = [
        HTTPRequest("GET", "/products/1"),
        HTTPRequest("GET", "/products/999"),
        HTTPRequest("GET", "/products/abc"),
    ]

    for request in requests:
        print(f"\nBrowser/client sends: {request.method} {request.target}")

        response = product_handler(request, service)

        print(
            f"Server returns: {response.status_code} {response.reason}"
        )
        print(f"Response body: {response.body}")


# ============================================================================
# 22. MAIN STUDY PROGRAM
# ============================================================================

def main() -> None:
    explain_architecture()
    demonstrate_url()
    demonstrate_http_messages()
    HTTPMethodDemo.show()
    explain_status_codes()
    demonstrate_routing()
    demonstrate_query_parameters()
    demonstrate_post_validation()
    demonstrate_sessions()
    demonstrate_password_storage()
    demonstrate_cache()
    demonstrate_etag()
    demonstrate_middleware()
    demonstrate_cors()
    demonstrate_lifecycle()
    run_real_http_server_demo()
    simulate_concurrent_requests()
    benchmark_lookup()
    demonstrate_security()
    demonstrate_production_architecture()
    demonstrate_end_to_end_case_study()

    section("Study program completed")

    print(
        "The demonstrations covered the path from browser interaction to "
        "HTTP transport, server routing, application processing, state, "
        "caching, security, concurrency, and response generation."
    )


if __name__ == "__main__":
    main()
