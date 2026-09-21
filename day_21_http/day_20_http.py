"""
HTTP: Requests, Responses, Methods, and Status Codes
=====================================================

A self-contained study program that teaches HTTP from absolute beginner
through advanced practical concepts.

The examples use only Python's standard library. No external packages
are required.

Run:
    python http_learning.py

The script can run a small local HTTP server and can also demonstrate
HTTP messages through an in-memory simulation.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# 1. HTTP FUNDAMENTALS
# ============================================================================

def explain_http_basics() -> None:
    print("\n" + "=" * 78)
    print("1. HTTP FUNDAMENTALS")
    print("=" * 78)

    print(
        """
HTTP stands for Hypertext Transfer Protocol.

It is an application-layer protocol used for communication between clients
and servers. A client sends an HTTP request. A server processes it and sends
an HTTP response.

A simplified exchange looks like:

    Client -> HTTP Request -> Server
    Client <- HTTP Response <- Server

A request commonly contains:
    - method
    - target URL/path
    - HTTP version
    - headers
    - optional body

A response commonly contains:
    - HTTP version
    - status code
    - reason phrase
    - headers
    - optional body

Example request:

    GET /users/42 HTTP/1.1
    Host: example.com
    Accept: application/json

Example response:

    HTTP/1.1 200 OK
    Content-Type: application/json

    {"id": 42, "name": "Ada"}

HTTP itself does not define a particular programming language or framework.
Browsers, mobile applications, command-line clients, Python programs,
JavaScript applications, and C++ programs can all communicate using HTTP.
"""
    )


# ============================================================================
# 2. METHODS
# ============================================================================

HTTP_METHODS = {
    "GET": "Retrieve a representation of a resource.",
    "POST": "Submit data, commonly creating a subordinate resource or triggering processing.",
    "PUT": "Create or completely replace the representation at a known target URI.",
    "PATCH": "Partially modify a resource.",
    "DELETE": "Remove a resource.",
    "HEAD": "Like GET, but normally returns headers without a response body.",
    "OPTIONS": "Discover communication options supported by a target.",
    "TRACE": "Diagnostic loop-back method; commonly disabled for security reasons.",
    "CONNECT": "Establish a tunnel, commonly through an HTTP proxy.",
}


def demonstrate_methods() -> None:
    print("\n" + "=" * 78)
    print("2. HTTP METHODS")
    print("=" * 78)

    for method, meaning in HTTP_METHODS.items():
        print(f"{method:8} {meaning}")

    print(
        """
Important properties:

GET, HEAD, PUT, and DELETE are defined as idempotent. Repeating the same
request should have the same intended effect on the server state, although
responses such as timestamps may differ.

GET, HEAD, PUT, DELETE, OPTIONS, and TRACE are safe methods in the HTTP
semantics. "Safe" means the request is intended for read-only semantics; it
does not mean the network operation has no side effects at all.

POST is not inherently idempotent. Sending the same POST twice may create
two resources or perform an operation twice.

PATCH is intended for partial modification. Its exact idempotency behavior
depends on the patch operation and API design.

Example resource-oriented API:

    GET    /users/42
    POST   /users
    PUT    /users/42
    PATCH  /users/42
    DELETE /users/42

A common mistake is using POST for every operation without considering the
semantics of the operation being performed.
"""
    )


# ============================================================================
# 3. STATUS CODES
# ============================================================================

STATUS_CODES = {
    100: "Continue",
    101: "Switching Protocols",
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    206: "Partial Content",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    412: "Precondition Failed",
    413: "Content Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def classify_status(code: int) -> str:
    if 100 <= code <= 199:
        return "1xx Informational"
    if 200 <= code <= 299:
        return "2xx Successful"
    if 300 <= code <= 399:
        return "3xx Redirection"
    if 400 <= code <= 499:
        return "4xx Client Error"
    if 500 <= code <= 599:
        return "5xx Server Error"
    return "Unknown status class"


def demonstrate_status_codes() -> None:
    print("\n" + "=" * 78)
    print("3. STATUS CODES")
    print("=" * 78)

    for code, phrase in STATUS_CODES.items():
        print(f"{code}: {phrase:28} -> {classify_status(code)}")

    print(
        """
The first digit gives the broad meaning:

1xx  Informational
2xx  Successful
3xx  Redirection
4xx  Client error
5xx  Server error

Important distinctions:

401 means authentication is required or authentication failed. It does not
literally mean "the user is not allowed"; 403 is commonly used when the
server understands the request but refuses to authorize it.

404 means the target resource was not found. APIs sometimes deliberately
return 404 for resources the caller is not allowed to discover.

405 means the method is not supported for the target resource.

409 commonly indicates a conflict with the current resource state.

422 is commonly used when the request is syntactically valid but the
submitted content fails application-level validation.

429 indicates rate limiting.

500 indicates an unexpected server-side failure.

502 and 504 are commonly generated by gateways or reverse proxies when
upstream services fail or do not respond appropriately.
"""
    )


# ============================================================================
# 4. REQUEST AND RESPONSE DATA MODELS
# ============================================================================

@dataclass
class HttpRequest:
    method: str
    target: str
    headers: Dict[str, str]
    body: bytes = b""

    def header(self, name: str) -> Optional[str]:
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None

    def text_body(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class HttpResponse:
    status_code: int
    reason: str
    headers: Dict[str, str]
    body: bytes = b""

    def text_body(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def demonstrate_message_structure() -> None:
    print("\n" + "=" * 78)
    print("4. HTTP MESSAGE STRUCTURE")
    print("=" * 78)

    request = HttpRequest(
        method="POST",
        target="/api/users?source=web",
        headers={
            "Host": "localhost:8000",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HTTP-Learning-Client/1.0",
        },
        body=json.dumps({"name": "Ada", "email": "ada@example.com"}).encode(),
    )

    response = HttpResponse(
        status_code=201,
        reason="Created",
        headers={
            "Content-Type": "application/json",
            "Location": "/api/users/101",
        },
        body=json.dumps({"id": 101, "name": "Ada"}).encode(),
    )

    print("REQUEST")
    print(f"Method: {request.method}")
    print(f"Target: {request.target}")
    print(f"Accept: {request.header('Accept')}")
    print(f"Body: {request.text_body()}")

    print("\nRESPONSE")
    print(f"Status: {response.status_code} {response.reason}")
    print(f"Content-Type: {response.headers['Content-Type']}")
    print(f"Body: {response.text_body()}")


# ============================================================================
# 5. URL, QUERY PARAMETERS, AND PATHS
# ============================================================================

def demonstrate_urls() -> None:
    print("\n" + "=" * 78)
    print("5. URLS, PATHS, AND QUERY PARAMETERS")
    print("=" * 78)

    url = (
        "https://example.com:8443/products/42"
        "?category=books&sort=price&page=2#details"
    )

    parsed = urllib.parse.urlparse(url)

    print(f"URL:       {url}")
    print(f"Scheme:    {parsed.scheme}")
    print(f"Host:      {parsed.hostname}")
    print(f"Port:      {parsed.port}")
    print(f"Path:      {parsed.path}")
    print(f"Query:     {parsed.query}")
    print(f"Fragment:  {parsed.fragment}")

    query = urllib.parse.parse_qs(parsed.query)
    print(f"Query map: {query}")

    rebuilt_query = urllib.parse.urlencode(
        {"search": "machine learning", "page": 2}
    )
    print(f"Encoded query: {rebuilt_query}")

    print(
        """
Path parameters identify resources:

    /users/42

Query parameters usually modify retrieval/filtering behavior:

    /users?role=admin&page=2

A fragment such as #details is normally handled by the user agent and is
not sent to the HTTP server in the request target.

URL encoding matters because spaces and reserved characters cannot simply
be inserted into every URL component.
"""
    )


# ============================================================================
# 6. JSON AND CONTENT TYPES
# ============================================================================

def demonstrate_content_types() -> None:
    print("\n" + "=" * 78)
    print("6. CONTENT TYPES AND JSON")
    print("=" * 78)

    user = {
        "id": 42,
        "name": "Ada Lovelace",
        "roles": ["engineer", "researcher"],
        "active": True,
    }

    encoded = json.dumps(user).encode("utf-8")

    print(f"Python object: {user}")
    print(f"JSON bytes:    {encoded}")
    print(f"Decoded JSON:  {json.loads(encoded.decode('utf-8'))}")

    print(
        """
Content-Type tells the receiver how to interpret the representation.

Common values include:

    application/json
    text/plain
    text/html
    application/xml
    application/x-www-form-urlencoded
    multipart/form-data

Content-Type describes the body being sent.

Accept describes representations the client can receive.

They are different:

    Content-Type: application/json
    Accept: application/json
"""
    )


# ============================================================================
# 7. LOCAL HTTP SERVER
# ============================================================================

class LearningRequestHandler(BaseHTTPRequestHandler):
    server_version = "HTTP-Learning-Server/1.0"

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        content_length = self.headers.get("Content-Length")

        if content_length is None:
            return None, "Missing Content-Length"

        try:
            length = int(content_length)
        except ValueError:
            return None, "Invalid Content-Length"

        if length < 0 or length > 1_000_000:
            return None, "Request body is too large"

        raw = self.rfile.read(length)

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "Invalid JSON"

        if not isinstance(data, dict):
            return None, "JSON body must be an object"

        return data, None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self._send_json(
                200,
                {
                    "message": "HTTP learning server",
                    "method": "GET",
                    "path": parsed.path,
                },
            )
            return

        if parsed.path == "/api/users":
            query = urllib.parse.parse_qs(parsed.query)
            name = query.get("name", [None])[0]

            users = [
                {"id": 1, "name": "Ada"},
                {"id": 2, "name": "Alan"},
                {"id": 3, "name": "Grace"},
            ]

            if name:
                users = [
                    user for user in users
                    if user["name"].lower() == name.lower()
                ]

            self._send_json(200, {"users": users})
            return

        if parsed.path.startswith("/api/users/"):
            user_id = parsed.path.rsplit("/", 1)[-1]

            if not user_id.isdigit():
                self._send_json(400, {"error": "Invalid user ID"})
                return

            if int(user_id) == 404:
                self._send_json(404, {"error": "User not found"})
                return

            self._send_json(
                200,
                {
                    "id": int(user_id),
                    "name": "Example User",
                },
            )
            return

        self._send_json(404, {"error": "Route not found"})

    def do_POST(self) -> None:
        if self.path != "/api/users":
            self._send_json(404, {"error": "Route not found"})
            return

        if self.headers.get_content_type() != "application/json":
            self._send_json(415, {"error": "Expected application/json"})
            return

        data, error = self._read_json_body()

        if error:
            self._send_json(400, {"error": error})
            return

        name = data.get("name")
        email = data.get("email")

        if not isinstance(name, str) or not name.strip():
            self._send_json(422, {"error": "name must be a non-empty string"})
            return

        if not isinstance(email, str) or "@" not in email:
            self._send_json(422, {"error": "email is invalid"})
            return

        self._send_json(
            201,
            {
                "message": "User created",
                "user": {
                    "id": 100,
                    "name": name.strip(),
                    "email": email.strip(),
                },
            },
        )

    def do_PUT(self) -> None:
        if not self.path.startswith("/api/users/"):
            self._send_json(404, {"error": "Route not found"})
            return

        user_id = self.path.rsplit("/", 1)[-1]

        if not user_id.isdigit():
            self._send_json(400, {"error": "Invalid user ID"})
            return

        data, error = self._read_json_body()

        if error:
            self._send_json(400, {"error": error})
            return

        if "name" not in data or "email" not in data:
            self._send_json(
                422,
                {"error": "PUT requires both name and email"},
            )
            return

        self._send_json(
            200,
            {
                "message": "User replaced",
                "id": int(user_id),
                "user": data,
            },
        )

    def do_PATCH(self) -> None:
        if not self.path.startswith("/api/users/"):
            self._send_json(404, {"error": "Route not found"})
            return

        data, error = self._read_json_body()

        if error:
            self._send_json(400, {"error": error})
            return

        allowed_fields = {"name", "email"}

        if not set(data).issubset(allowed_fields):
            self._send_json(422, {"error": "Unsupported field"})
            return

        self._send_json(
            200,
            {
                "message": "User partially updated",
                "changes": data,
            },
        )

    def do_DELETE(self) -> None:
        if not self.path.startswith("/api/users/"):
            self._send_json(404, {"error": "Route not found"})
            return

        user_id = self.path.rsplit("/", 1)[-1]

        if not user_id.isdigit():
            self._send_json(400, {"error": "Invalid user ID"})
            return

        self.send_response(204)
        self.end_headers()

    def do_HEAD(self) -> None:
        if self.path == "/":
            body = b""
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header(
            "Allow",
            "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS",
        )
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[SERVER] {self.address_string()} - {format % args}")


def start_local_server() -> Tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), LearningRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


# ============================================================================
# 8. HTTP CLIENT
# ============================================================================

def request_with_urllib(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, str], str]:
    body = None

    headers = {
        "Accept": "application/json",
        "User-Agent": "Python-HTTP-Learning-Client/1.0",
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            response_body = response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )

            return (
                response.status,
                dict(response.headers.items()),
                response_body,
            )

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        return error.code, dict(error.headers.items()), error_body

    except urllib.error.URLError as error:
        return 0, {}, f"Connection error: {error.reason}"


def demonstrate_real_http_requests() -> None:
    print("\n" + "=" * 78)
    print("8. REAL LOCAL HTTP REQUESTS")
    print("=" * 78)

    server, thread = start_local_server()
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"

    print(f"Local server started at {base_url}")

    try:
        tests = [
            ("GET", f"{base_url}/", None),
            ("GET", f"{base_url}/api/users?name=Ada", None),
            (
                "POST",
                f"{base_url}/api/users",
                {"name": "Katherine", "email": "katherine@example.com"},
            ),
            (
                "PUT",
                f"{base_url}/api/users/10",
                {"name": "Updated", "email": "updated@example.com"},
            ),
            (
                "PATCH",
                f"{base_url}/api/users/10",
                {"name": "Partially Updated"},
            ),
            ("DELETE", f"{base_url}/api/users/10", None),
            ("OPTIONS", f"{base_url}/", None),
            ("GET", f"{base_url}/api/users/404", None),
        ]

        for method, url, payload in tests:
            status, headers, body = request_with_urllib(
                url,
                method,
                payload,
            )

            print(f"\n{method} {url}")
            print(f"Status: {status} {STATUS_CODES.get(status, '')}")
            print(f"Content-Type: {headers.get('Content-Type', '<none>')}")
            print(f"Body: {body}")

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        print("\nLocal server stopped.")


# ============================================================================
# 9. VALIDATION AND ERROR HANDLING
# ============================================================================

def validate_request(
    method: str,
    content_type: Optional[str],
    body: Optional[bytes],
) -> List[str]:
    errors: List[str] = []

    if method not in HTTP_METHODS:
        errors.append("Unsupported HTTP method")

    if method in {"POST", "PUT", "PATCH"}:
        if not content_type:
            errors.append("Missing Content-Type")
        elif content_type.split(";")[0].strip().lower() != "application/json":
            errors.append("Expected application/json")

        if body is None or not body:
            errors.append("Request body is required")

    return errors


def demonstrate_validation() -> None:
    print("\n" + "=" * 78)
    print("9. VALIDATION AND ERROR HANDLING")
    print("=" * 78)

    cases = [
        ("POST", "application/json", b'{"name":"Ada"}'),
        ("POST", None, b'{"name":"Ada"}'),
        ("PATCH", "text/plain", b"name=Ada"),
        ("GET", None, None),
    ]

    for method, content_type, body in cases:
        errors = validate_request(method, content_type, body)
        print(
            f"{method:6} content_type={str(content_type):20} "
            f"errors={errors or 'none'}"
        )

    print(
        """
A robust client should distinguish:

    - DNS/connectivity failures
    - TLS failures
    - timeout failures
    - malformed HTTP responses
    - 4xx application/client errors
    - 5xx server errors

A 404 is an HTTP response. A connection timeout is not a 404.

This distinction is important when designing retries and monitoring.
"""
    )


# ============================================================================
# 10. RETRIES AND IDEMPOTENCY
# ============================================================================

def should_retry(
    method: str,
    status_code: int,
    attempt: int,
    max_attempts: int,
) -> bool:
    if attempt >= max_attempts:
        return False

    retryable_statuses = {408, 429, 500, 502, 503, 504}

    if status_code not in retryable_statuses:
        return False

    # Automatically retrying a non-idempotent operation can create duplicate
    # effects. POST may be retried safely only when the application has an
    # explicit mechanism such as an idempotency key.
    if method not in {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}:
        return False

    return True


def demonstrate_retry_policy() -> None:
    print("\n" + "=" * 78)
    print("10. RETRIES AND IDEMPOTENCY")
    print("=" * 78)

    scenarios = [
        ("GET", 503),
        ("POST", 503),
        ("PUT", 503),
        ("GET", 404),
        ("DELETE", 429),
    ]

    for method, status in scenarios:
        result = should_retry(method, status, 1, 3)
        print(f"{method:6} {status}: retry={result}")

    print(
        """
A retry policy should consider:

    - HTTP method
    - status code
    - timeout/network failure
    - attempt count
    - exponential backoff
    - jitter
    - Retry-After
    - idempotency
    - application-specific semantics

A naive "retry everything" strategy can amplify outages and duplicate
non-idempotent operations.
"""
    )


# ============================================================================
# 11. CACHING CONCEPTS
# ============================================================================

def demonstrate_cache_headers() -> None:
    print("\n" + "=" * 78)
    print("11. HTTP CACHING")
    print("=" * 78)

    response_headers = {
        "Cache-Control": "public, max-age=60",
        "ETag": '"resource-v7"',
        "Last-Modified": "Mon, 21 Sep 2026 05:30:00 GMT",
    }

    conditional_request_headers = {
        "If-None-Match": '"resource-v7"',
    }

    print("Response headers:")
    for key, value in response_headers.items():
        print(f"  {key}: {value}")

    print("\nConditional request:")
    for key, value in conditional_request_headers.items():
        print(f"  {key}: {value}")

    print(
        """
If the representation has not changed, the server can respond with 304
Not Modified instead of retransmitting the complete representation.

ETag provides a validator for a representation.

Cache-Control controls caching behavior.

Caching can reduce latency, bandwidth usage, server load, and database load,
but incorrect cache configuration can expose stale or private information.
"""
    )


# ============================================================================
# 12. AUTHENTICATION AND SECURITY
# ============================================================================

def demonstrate_security() -> None:
    print("\n" + "=" * 78)
    print("12. HTTP SECURITY")
    print("=" * 78)

    safe_headers = {
        "Authorization": "Bearer <access-token>",
        "Content-Type": "application/json",
        "Origin": "https://app.example.com",
    }

    for key, value in safe_headers.items():
        print(f"{key}: {value}")

    print(
        """
HTTPS is HTTP carried over TLS. TLS provides encryption, integrity, and
server authentication when configured correctly.

Never place credentials or tokens in URLs when a safer header/body mechanism
is available, because URLs may be recorded in logs, browser history,
monitoring systems, and other infrastructure.

Common HTTP/application security concerns include:

    - missing TLS
    - broken authentication
    - broken authorization
    - insecure CORS configuration
    - request smuggling
    - header injection
    - cache poisoning
    - CSRF
    - XSS through HTML responses
    - oversized request bodies
    - rate-limit abuse
    - sensitive information in error responses

HTTP status codes themselves are not an authorization system. The server
must enforce authentication and authorization independently.
"""
    )


# ============================================================================
# 13. PERFORMANCE
# ============================================================================

def demonstrate_performance() -> None:
    print("\n" + "=" * 78)
    print("13. PERFORMANCE CONSIDERATIONS")
    print("=" * 78)

    resources = {
        "DNS lookup": 5,
        "TCP/TLS connection": 30,
        "server processing": 20,
        "response transfer": 15,
    }

    total = sum(resources.values())

    for stage, milliseconds in resources.items():
        print(f"{stage:24}: {milliseconds:4} ms")

    print(f"Approximate total: {total} ms")

    print(
        """
Real HTTP latency can include DNS, connection establishment, TLS negotiation,
request transmission, server processing, upstream calls, and response
transmission.

Performance techniques include:

    - connection reuse
    - HTTP/2 multiplexing
    - HTTP/3 over QUIC
    - compression
    - caching
    - pagination
    - avoiding unnecessarily large payloads
    - efficient server-side processing
    - appropriate timeouts
    - connection pooling

Payload size matters too. Sending thousands of unused fields can increase
network cost and serialization/deserialization work.
"""
    )


# ============================================================================
# 14. HTTP/1.1, HTTP/2, HTTP/3 CONCEPTS
# ============================================================================

def demonstrate_http_versions() -> None:
    print("\n" + "=" * 78)
    print("14. HTTP VERSIONS")
    print("=" * 78)

    versions = {
        "HTTP/1.0": "Introduced persistent HTTP evolution but generally had simpler connection behavior.",
        "HTTP/1.1": "Added persistent connections and standardized important request/response behavior.",
        "HTTP/2": "Uses binary framing and multiplexes streams over a connection.",
        "HTTP/3": "Uses HTTP semantics over QUIC, which runs over UDP.",
    }

    for version, description in versions.items():
        print(f"{version:9} {description}")

    print(
        """
HTTP/2 and HTTP/3 retain HTTP semantics such as methods, status codes, URIs,
headers, and representations. Their transport/framing mechanisms differ.

Application developers should not assume that "HTTP/2" or "HTTP/3" means the
request semantics have changed into a completely different API model.
"""
    )


# ============================================================================
# 15. MINI API CLIENT
# ============================================================================

class SimpleApiClient:
    def __init__(self, base_url: str, timeout: float = 3.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not path.startswith("/"):
            raise ValueError("path must begin with '/'")

        url = self.base_url + path

        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "SimpleApiClient/1.0",
        }

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url=url,
            method=method.upper(),
            headers=headers,
            data=body,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw = response.read()
                content_type = response.headers.get_content_type()

                result: Dict[str, Any] = {
                    "status": response.status,
                    "headers": dict(response.headers.items()),
                }

                if content_type == "application/json":
                    result["body"] = json.loads(raw.decode("utf-8"))
                else:
                    result["body"] = raw.decode("utf-8", errors="replace")

                return result

        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                body_value: Any = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body_value = raw.decode("utf-8", errors="replace")

            return {
                "status": error.code,
                "headers": dict(error.headers.items()),
                "body": body_value,
            }

        except urllib.error.URLError as error:
            raise ConnectionError(str(error.reason)) from error


def demonstrate_api_client() -> None:
    print("\n" + "=" * 78)
    print("15. MINI API CLIENT")
    print("=" * 78)

    server, thread = start_local_server()
    client = SimpleApiClient(f"http://127.0.0.1:{server.server_port}")

    try:
        result = client.request("GET", "/api/users")
        print("GET result:")
        print(json.dumps(result, indent=2))

        result = client.request(
            "POST",
            "/api/users",
            {"name": "Grace", "email": "grace@example.com"},
        )
        print("\nPOST result:")
        print(json.dumps(result, indent=2))

        result = client.request(
            "POST",
            "/api/users",
            {"name": "", "email": "invalid"},
        )
        print("\nValidation error:")
        print(json.dumps(result, indent=2))

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


# ============================================================================
# 16. TESTS
# ============================================================================

def run_tests() -> None:
    print("\n" + "=" * 78)
    print("16. BASIC TESTS")
    print("=" * 78)

    assert classify_status(200) == "2xx Successful"
    assert classify_status(404) == "4xx Client Error"
    assert classify_status(503) == "5xx Server Error"

    request = HttpRequest(
        method="GET",
        target="/",
        headers={"Content-Type": "application/json"},
    )

    assert request.header("content-type") == "application/json"

    errors = validate_request(
        "POST",
        "application/json",
        b'{"name":"Ada"}',
    )

    assert errors == []

    assert should_retry("GET", 503, 1, 3)
    assert not should_retry("POST", 503, 1, 3)
    assert not should_retry("GET", 404, 1, 3)

    print("All tests passed.")


# ============================================================================
# 17. PRACTICAL STUDY CHECKLIST
# ============================================================================

def print_study_checklist() -> None:
    print("\n" + "=" * 78)
    print("17. PRACTICAL STUDY CHECKLIST")
    print("=" * 78)

    checklist = [
        "Understand client-server communication.",
        "Identify method, target, headers, and body in a request.",
        "Identify status code, headers, and body in a response.",
        "Understand the 1xx through 5xx status classes.",
        "Distinguish GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS.",
        "Understand Content-Type versus Accept.",
        "Understand path parameters versus query parameters.",
        "Understand safe and idempotent methods.",
        "Handle 4xx and 5xx responses correctly.",
        "Separate network failures from HTTP errors.",
        "Understand timeouts and retry safety.",
        "Understand caching and conditional requests.",
        "Understand HTTPS and common HTTP security risks.",
        "Understand basic HTTP/1.1, HTTP/2, and HTTP/3 differences.",
        "Build and test a small HTTP client/server interaction.",
    ]

    for number, item in enumerate(checklist, 1):
        print(f"{number:2}. {item}")


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    print("=" * 78)
    print("HTTP LEARNING LAB")
    print("Requests, Responses, Methods, and Status Codes")
    print("=" * 78)

    explain_http_basics()
    demonstrate_methods()
    demonstrate_status_codes()
    demonstrate_message_structure()
    demonstrate_urls()
    demonstrate_content_types()
    demonstrate_real_http_requests()
    demonstrate_validation()
    demonstrate_retry_policy()
    demonstrate_cache_headers()
    demonstrate_security()
    demonstrate_performance()
    demonstrate_http_versions()
    demonstrate_api_client()
    run_tests()
    print_study_checklist()

    print("\n" + "=" * 78)
    print("HTTP learning program completed.")
    print("=" * 78)


if __name__ == "__main__":
    main()
