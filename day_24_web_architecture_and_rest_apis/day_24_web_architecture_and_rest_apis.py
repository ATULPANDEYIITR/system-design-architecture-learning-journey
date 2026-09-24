"""
Web Architecture and REST APIs
Resources, Endpoints, HTTP Methods, and Statelessness

A self-contained study and executable demonstration covering REST API
fundamentals through advanced design considerations.

Run:
    python rest_api_architecture.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import re
import time
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple


# =============================================================================
# 1. FUNDAMENTAL TERMINOLOGY
# =============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain_term(term: str, definition: str) -> None:
    print(f"{term}: {definition}")


def fundamentals_demo() -> None:
    section("1. REST API fundamentals")

    explain_term(
        "Web architecture",
        "The organization of clients, servers, resources, protocols, and "
        "intermediaries that cooperate to deliver web functionality.",
    )
    explain_term(
        "API",
        "An Application Programming Interface is a defined contract through "
        "which software components communicate.",
    )
    explain_term(
        "REST",
        "Representational State Transfer is an architectural style based on "
        "constraints such as client-server separation, statelessness, "
        "cacheability, a uniform interface, layered systems, and resource "
        "identification.",
    )
    explain_term(
        "Resource",
        "A conceptual entity exposed by an API, such as a user, product, "
        "order, article, or collection of products.",
    )
    explain_term(
        "Endpoint",
        "A URI/URL and HTTP interaction through which a client accesses a "
        "resource or collection.",
    )
    explain_term(
        "Representation",
        "A transferable representation of a resource, commonly JSON in "
        "modern REST APIs.",
    )
    explain_term(
        "Statelessness",
        "Each request contains the information required for the server to "
        "process it; the server does not rely on application session state "
        "stored between requests.",
    )

    print("\nTypical resource-oriented API structure:")
    examples = [
        "GET    /api/v1/products",
        "GET    /api/v1/products/42",
        "POST   /api/v1/products",
        "PATCH  /api/v1/products/42",
        "DELETE /api/v1/products/42",
    ]

    for example in examples:
        print("  " + example)


# =============================================================================
# 2. RESOURCE MODEL
# =============================================================================

@dataclass
class Product:
    product_id: int
    name: str
    category: str
    price: float
    stock: int
    active: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.product_id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "stock": self.stock,
            "active": self.active,
            "created_at": self.created_at,
        }


def resource_demo() -> None:
    section("2. Resources and representations")

    product = Product(
        product_id=101,
        name="Mechanical Keyboard",
        category="electronics",
        price=3499.0,
        stock=25,
    )

    representation = product.to_dict()

    print("Resource object:")
    print(product)

    print("\nJSON representation:")
    print(json.dumps(representation, indent=2))

    print(
        "\nThe resource is the conceptual product. "
        "The JSON object is one transferable representation of that resource."
    )


# =============================================================================
# 3. URI AND ENDPOINT DESIGN
# =============================================================================

def endpoint_design_demo() -> None:
    section("3. URI and endpoint design")

    valid_patterns = [
        "/api/v1/products",
        "/api/v1/products/101",
        "/api/v1/products/101/reviews",
        "/api/v1/products/101/reviews/7",
    ]

    print("Resource-oriented URI examples:")
    for uri in valid_patterns:
        print(f"  {uri}")

    print("\nCommon design principles:")
    principles = [
        "Use nouns to identify resources.",
        "Use HTTP methods to describe the requested operation.",
        "Use path parameters to identify a specific resource.",
        "Use query parameters for filtering, sorting, pagination, and search.",
        "Use plural collection names consistently.",
        "Version APIs deliberately when compatibility requires it.",
        "Avoid embedding an operation name in every URI.",
    ]

    for principle in principles:
        print(f"  - {principle}")

    print("\nExamples of query parameters:")
    print("  /api/v1/products?category=electronics")
    print("  /api/v1/products?min_price=1000&max_price=5000")
    print("  /api/v1/products?page=2&limit=20")
    print("  /api/v1/products?sort=-price")


# =============================================================================
# 4. HTTP METHODS
# =============================================================================

class HttpMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


def method_properties_demo() -> None:
    section("4. HTTP methods")

    properties = {
        "GET": {
            "purpose": "Retrieve a representation",
            "safe": True,
            "idempotent": True,
        },
        "POST": {
            "purpose": "Create a subordinate resource or perform a non-idempotent action",
            "safe": False,
            "idempotent": False,
        },
        "PUT": {
            "purpose": "Replace a resource representation",
            "safe": False,
            "idempotent": True,
        },
        "PATCH": {
            "purpose": "Partially modify a resource",
            "safe": False,
            "idempotent": "Depends on operation design",
        },
        "DELETE": {
            "purpose": "Remove a resource",
            "safe": False,
            "idempotent": True,
        },
        "HEAD": {
            "purpose": "Retrieve headers without a response body",
            "safe": True,
            "idempotent": True,
        },
        "OPTIONS": {
            "purpose": "Discover communication options",
            "safe": True,
            "idempotent": True,
        },
    }

    for method, information in properties.items():
        print(f"\n{method}")
        for key, value in information.items():
            print(f"  {key}: {value}")

    print("\nImportant distinction:")
    print("  Safe does not mean 'secure'.")
    print("  Idempotent does not mean 'the request has no side effects'.")
    print("  Idempotence concerns the intended effect of repeating a request.")


# =============================================================================
# 5. HTTP REQUEST AND RESPONSE MODEL
# =============================================================================

@dataclass
class HttpRequest:
    method: HttpMethod
    path: str
    headers: Dict[str, str] = field(default_factory=dict)
    query: Dict[str, str] = field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None


@dataclass
class HttpResponse:
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None

    def to_http_like_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status_code,
            "headers": self.headers,
            "body": self.body,
        }


def http_message_demo() -> None:
    section("5. HTTP request and response")

    request = HttpRequest(
        method=HttpMethod.GET,
        path="/api/v1/products/101",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer example-token",
        },
    )

    response = HttpResponse(
        status_code=200,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "max-age=60",
        },
        body={
            "id": 101,
            "name": "Mechanical Keyboard",
            "price": 3499.0,
        },
    )

    print("Request:")
    print(json.dumps({
        "method": request.method.value,
        "path": request.path,
        "headers": request.headers,
        "body": request.body,
    }, indent=2))

    print("\nResponse:")
    print(json.dumps(response.to_http_like_dict(), indent=2))


# =============================================================================
# 6. STATUS CODES
# =============================================================================

def status_code_demo() -> None:
    section("6. HTTP status codes")

    statuses = {
        200: "OK - successful request",
        201: "Created - resource successfully created",
        202: "Accepted - request accepted for asynchronous processing",
        204: "No Content - successful response with no body",
        304: "Not Modified - cached representation remains valid",
        400: "Bad Request - invalid request syntax or data",
        401: "Unauthorized - authentication is required or invalid",
        403: "Forbidden - request understood but not permitted",
        404: "Not Found - resource does not exist",
        409: "Conflict - request conflicts with current resource state",
        412: "Precondition Failed - a conditional request failed",
        415: "Unsupported Media Type",
        422: "Unprocessable Content - semantically invalid input",
        429: "Too Many Requests - rate limit exceeded",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    for code, meaning in statuses.items():
        print(f"{code}: {meaning}")


# =============================================================================
# 7. VALIDATION AND ERROR REPRESENTATION
# =============================================================================

class ApiValidationError(Exception):
    """Represents a client-side validation failure."""

    def __init__(self, errors: Dict[str, str]):
        super().__init__("Request validation failed")
        self.errors = errors


def validate_product_payload(payload: Mapping[str, Any]) -> None:
    errors: Dict[str, str] = {}

    if not isinstance(payload.get("name"), str):
        errors["name"] = "name must be a string"
    elif not payload["name"].strip():
        errors["name"] = "name must not be empty"

    price = payload.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool):
        errors["price"] = "price must be numeric"
    elif price < 0:
        errors["price"] = "price must not be negative"

    stock = payload.get("stock")
    if not isinstance(stock, int) or isinstance(stock, bool):
        errors["stock"] = "stock must be an integer"
    elif stock < 0:
        errors["stock"] = "stock must not be negative"

    if errors:
        raise ApiValidationError(errors)


def validation_demo() -> None:
    section("7. Validation and structured errors")

    invalid_payload = {
        "name": "",
        "price": -10,
        "stock": "many",
    }

    try:
        validate_product_payload(invalid_payload)
    except ApiValidationError as error:
        response = HttpResponse(
            status_code=422,
            headers={"Content-Type": "application/json"},
            body={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(error),
                    "fields": error.errors,
                }
            },
        )
        print(json.dumps(response.to_http_like_dict(), indent=2))


# =============================================================================
# 8. IN-MEMORY REST SERVICE
# =============================================================================

class ProductRepository:
    """Repository abstraction separating storage operations from HTTP logic."""

    def __init__(self) -> None:
        self._products: Dict[int, Product] = {}
        self._next_id = 1

    def create(
        self,
        name: str,
        category: str,
        price: float,
        stock: int,
    ) -> Product:
        product = Product(
            product_id=self._next_id,
            name=name,
            category=category,
            price=price,
            stock=stock,
        )
        self._products[self._next_id] = product
        self._next_id += 1
        return product

    def get(self, product_id: int) -> Optional[Product]:
        return self._products.get(product_id)

    def list(self) -> List[Product]:
        return list(self._products.values())

    def replace(self, product_id: int, **fields: Any) -> Optional[Product]:
        product = self.get(product_id)
        if product is None:
            return None

        self._products[product_id] = Product(
            product_id=product_id,
            name=fields["name"],
            category=fields["category"],
            price=fields["price"],
            stock=fields["stock"],
            active=fields.get("active", True),
            created_at=product.created_at,
        )
        return self._products[product_id]

    def patch(self, product_id: int, **fields: Any) -> Optional[Product]:
        product = self.get(product_id)
        if product is None:
            return None

        for field_name, value in fields.items():
            if hasattr(product, field_name):
                setattr(product, field_name, value)

        return product

    def delete(self, product_id: int) -> bool:
        return self._products.pop(product_id, None) is not None


class ProductApi:
    """Resource-oriented service layer."""

    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def get_products(
        self,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        page: int = 1,
        limit: int = 10,
    ) -> HttpResponse:
        if page < 1 or limit < 1 or limit > 100:
            return HttpResponse(
                400,
                body={
                    "error": {
                        "code": "INVALID_PAGINATION",
                        "message": "page must be >= 1 and limit must be 1..100",
                    }
                },
            )

        products = self.repository.list()

        if category is not None:
            products = [
                product for product in products
                if product.category.lower() == category.lower()
            ]

        if min_price is not None:
            products = [
                product for product in products
                if product.price >= min_price
            ]

        if max_price is not None:
            products = [
                product for product in products
                if product.price <= max_price
            ]

        start = (page - 1) * limit
        end = start + limit
        page_items = products[start:end]

        return HttpResponse(
            200,
            headers={"Content-Type": "application/json"},
            body={
                "data": [product.to_dict() for product in page_items],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": len(products),
                    "pages": (
                        (len(products) + limit - 1) // limit
                        if products else 0
                    ),
                },
            },
        )

    def get_product(self, product_id: int) -> HttpResponse:
        product = self.repository.get(product_id)

        if product is None:
            return HttpResponse(
                404,
                body={
                    "error": {
                        "code": "PRODUCT_NOT_FOUND",
                        "message": f"Product {product_id} was not found",
                    }
                },
            )

        return HttpResponse(
            200,
            headers={"Content-Type": "application/json"},
            body={"data": product.to_dict()},
        )

    def create_product(self, payload: Mapping[str, Any]) -> HttpResponse:
        try:
            validate_product_payload(payload)
        except ApiValidationError as error:
            return HttpResponse(
                422,
                body={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "fields": error.errors,
                    }
                },
            )

        product = self.repository.create(
            name=payload["name"].strip(),
            category=str(payload.get("category", "uncategorized")).strip(),
            price=float(payload["price"]),
            stock=int(payload["stock"]),
        )

        return HttpResponse(
            201,
            headers={
                "Content-Type": "application/json",
                "Location": f"/api/v1/products/{product.product_id}",
            },
            body={"data": product.to_dict()},
        )

    def patch_product(
        self,
        product_id: int,
        payload: Mapping[str, Any],
    ) -> HttpResponse:
        product = self.repository.get(product_id)

        if product is None:
            return HttpResponse(404, body={
                "error": {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Product does not exist",
                }
            })

        allowed = {"name", "category", "price", "stock", "active"}
        unknown = set(payload) - allowed

        if unknown:
            return HttpResponse(400, body={
                "error": {
                    "code": "UNKNOWN_FIELD",
                    "message": f"Unknown fields: {sorted(unknown)}",
                }
            })

        updated = self.repository.patch(product_id, **dict(payload))

        return HttpResponse(
            200,
            headers={"Content-Type": "application/json"},
            body={"data": updated.to_dict()},
        )

    def delete_product(self, product_id: int) -> HttpResponse:
        if not self.repository.delete(product_id):
            return HttpResponse(404, body={
                "error": {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Product does not exist",
                }
            })

        return HttpResponse(204)


def rest_service_demo() -> None:
    section("8. Complete resource-oriented service demonstration")

    repository = ProductRepository()
    api = ProductApi(repository)

    print("POST /api/v1/products")
    create_response = api.create_product({
        "name": "Mechanical Keyboard",
        "category": "electronics",
        "price": 3499,
        "stock": 25,
    })
    print(json.dumps(create_response.to_http_like_dict(), indent=2))

    print("\nPOST /api/v1/products")
    second_response = api.create_product({
        "name": "USB-C Hub",
        "category": "electronics",
        "price": 1499,
        "stock": 40,
    })
    print(json.dumps(second_response.to_http_like_dict(), indent=2))

    print("\nGET /api/v1/products?category=electronics")
    list_response = api.get_products(category="electronics")
    print(json.dumps(list_response.to_http_like_dict(), indent=2))

    product_id = create_response.body["data"]["id"]

    print(f"\nGET /api/v1/products/{product_id}")
    print(json.dumps(
        api.get_product(product_id).to_http_like_dict(),
        indent=2,
    ))

    print(f"\nPATCH /api/v1/products/{product_id}")
    patch_response = api.patch_product(
        product_id,
        {"price": 3299, "stock": 30},
    )
    print(json.dumps(patch_response.to_http_like_dict(), indent=2))

    print(f"\nGET /api/v1/products/{product_id}")
    print(json.dumps(
        api.get_product(product_id).to_http_like_dict(),
        indent=2,
    ))

    print("\nGET /api/v1/products/9999")
    print(json.dumps(
        api.get_product(9999).to_http_like_dict(),
        indent=2,
    ))


# =============================================================================
# 9. PUT VERSUS PATCH
# =============================================================================

def put_patch_demo() -> None:
    section("9. PUT versus PATCH")

    resource = {
        "id": 7,
        "name": "Monitor",
        "category": "electronics",
        "price": 20000,
        "stock": 10,
    }

    print("Original resource:")
    print(json.dumps(resource, indent=2))

    put_payload = {
        "name": "4K Monitor",
        "category": "electronics",
        "price": 22000,
        "stock": 8,
    }

    replaced = {
        "id": resource["id"],
        **put_payload,
    }

    print("\nPUT replacement:")
    print(json.dumps(replaced, indent=2))

    patch_payload = {"price": 21000}
    patched = {**resource, **patch_payload}

    print("\nPATCH modification:")
    print(json.dumps(patched, indent=2))

    print(
        "\nPUT is conceptually a complete replacement representation, "
        "while PATCH describes partial modification."
    )


# =============================================================================
# 10. STATELESSNESS
# =============================================================================

@dataclass
class StatelessRequest:
    method: str
    path: str
    authorization: Optional[str]
    body: Optional[Dict[str, Any]] = None


class StatelessApi:
    """
    A stateless API does not need a server-side conversational session to
    remember who the client is between requests. Each request carries the
    authentication information needed for authorization.
    """

    def __init__(self) -> None:
        self.valid_tokens = {
            "token-user-1": {"user_id": 1, "role": "customer"},
            "token-admin": {"user_id": 2, "role": "admin"},
        }

    def authenticate(
        self,
        request: StatelessRequest,
    ) -> Optional[Dict[str, Any]]:
        if not request.authorization:
            return None

        scheme, _, token = request.authorization.partition(" ")

        if scheme.lower() != "bearer":
            return None

        return self.valid_tokens.get(token)

    def handle(self, request: StatelessRequest) -> HttpResponse:
        identity = self.authenticate(request)

        if identity is None:
            return HttpResponse(
                401,
                headers={"WWW-Authenticate": "Bearer"},
                body={
                    "error": {
                        "code": "UNAUTHENTICATED",
                        "message": "Valid authentication credentials are required",
                    }
                },
            )

        return HttpResponse(
            200,
            body={
                "data": {
                    "message": "Request authenticated",
                    "user_id": identity["user_id"],
                    "role": identity["role"],
                }
            },
        )


def statelessness_demo() -> None:
    section("10. Statelessness")

    api = StatelessApi()

    requests = [
        StatelessRequest(
            method="GET",
            path="/api/v1/account",
            authorization="Bearer token-user-1",
        ),
        StatelessRequest(
            method="GET",
            path="/api/v1/account",
            authorization=None,
        ),
        StatelessRequest(
            method="GET",
            path="/api/v1/account",
            authorization="Bearer invalid-token",
        ),
    ]

    for request in requests:
        response = api.handle(request)
        print(f"\n{request.method} {request.path}")
        print(json.dumps(response.to_http_like_dict(), indent=2))

    print(
        "\nThe important architectural point is that request processing "
        "does not depend on a hidden server-side conversation state."
    )


# =============================================================================
# 11. IDEMPOTENCE
# =============================================================================

class InventoryService:
    def __init__(self) -> None:
        self.stock = 10

    def delete_reservation(self) -> None:
        # Repeating the operation after the reservation is already absent
        # leaves the resource in the same intended final state.
        self.stock = max(0, self.stock)

    def purchase(self, quantity: int) -> None:
        # A naïve POST-like operation is not idempotent because repeating it
        # can create another purchase.
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if quantity > self.stock:
            raise ValueError("insufficient stock")
        self.stock -= quantity


def idempotence_demo() -> None:
    section("11. Idempotence")

    inventory = InventoryService()

    print(f"Initial stock: {inventory.stock}")
    inventory.delete_reservation()
    inventory.delete_reservation()
    print(f"Stock after repeated idempotent-style delete operation: {inventory.stock}")

    print("\nPOST-style purchase:")
    inventory.purchase(2)
    print(f"Stock after first purchase: {inventory.stock}")

    try:
        inventory.purchase(2)
        print(f"Stock after repeated purchase: {inventory.stock}")
    except ValueError as error:
        print(f"Second operation failed: {error}")

    print(
        "\nAn idempotent HTTP method can be safely retried at the semantic "
        "resource-state level, although network retries still require careful "
        "application design."
    )


# =============================================================================
# 12. IDEMPOTENCY KEYS
# =============================================================================

class PaymentService:
    """
    Idempotency keys allow a server to recognize a retried client operation.

    This is especially useful for operations such as payments where sending
    the same POST request twice must not create two charges.
    """

    def __init__(self) -> None:
        self.processed_keys: Dict[str, Dict[str, Any]] = {}
        self.next_payment_id = 1000

    def create_payment(
        self,
        amount: float,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        if not idempotency_key.strip():
            raise ValueError("idempotency key is required")

        if idempotency_key in self.processed_keys:
            return self.processed_keys[idempotency_key]

        if amount <= 0:
            raise ValueError("payment amount must be positive")

        payment = {
            "payment_id": self.next_payment_id,
            "amount": amount,
            "status": "accepted",
        }

        self.next_payment_id += 1
        self.processed_keys[idempotency_key] = payment
        return payment


def idempotency_key_demo() -> None:
    section("12. Idempotency keys")

    service = PaymentService()
    key = "checkout-2026-000001"

    first = service.create_payment(999.0, key)
    second = service.create_payment(999.0, key)

    print("First request:")
    print(first)

    print("\nRetry using the same idempotency key:")
    print(second)

    print(
        "\nThe second request returns the previously recorded result instead "
        "of creating another payment."
    )


# =============================================================================
# 13. QUERY PARAMETERS, FILTERING, SORTING, PAGINATION
# =============================================================================

def advanced_query_demo() -> None:
    section("13. Filtering, sorting, and pagination")

    repository = ProductRepository()

    sample_products = [
        ("Keyboard", "electronics", 3500, 20),
        ("Mouse", "electronics", 1200, 50),
        ("Desk", "furniture", 8000, 5),
        ("Monitor", "electronics", 22000, 10),
        ("Chair", "furniture", 12000, 7),
    ]

    for item in sample_products:
        repository.create(*item)

    products = repository.list()

    filtered = [
        product for product in products
        if product.category == "electronics"
        and product.price <= 10000
    ]

    sorted_products = sorted(
        filtered,
        key=lambda product: product.price,
        reverse=True,
    )

    page_size = 2
    page = 1
    start = (page - 1) * page_size
    page_items = sorted_products[start:start + page_size]

    print("Query semantics:")
    print("  category = electronics")
    print("  max_price = 10000")
    print("  sort = -price")
    print("  page = 1")
    print("  limit = 2")

    print("\nResult:")
    for product in page_items:
        print(product.to_dict())


# =============================================================================
# 14. CACHING AND CONDITIONAL REQUESTS
# =============================================================================

@dataclass
class CachedRepresentation:
    body: Dict[str, Any]
    etag: str
    created_at: float


def create_etag(body: Mapping[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    # This is only a teaching example. Production ETags should be designed
    # according to the application's representation and caching requirements.
    return str(hash(canonical))


def caching_demo() -> None:
    section("14. Caching and conditional requests")

    representation = {
        "id": 101,
        "name": "Mechanical Keyboard",
        "price": 3499,
    }

    etag = create_etag(representation)

    print(f"Generated representation tag: {etag}")
    print("Response headers might contain:")
    print("  Cache-Control: max-age=60")
    print(f"  ETag: {etag}")

    client_etag = etag

    if client_etag == etag:
        response = HttpResponse(
            304,
            headers={"ETag": etag},
            body=None,
        )
    else:
        response = HttpResponse(
            200,
            headers={"ETag": etag},
            body=representation,
        )

    print("\nConditional GET result:")
    print(json.dumps(response.to_http_like_dict(), indent=2))


# =============================================================================
# 15. CONTENT NEGOTIATION
# =============================================================================

def content_negotiation_demo() -> None:
    section("15. Content negotiation")

    supported_media_types = [
        "application/json",
        "application/problem+json",
    ]

    client_accept = "application/json"

    print(f"Client Accept: {client_accept}")
    print(f"Server supports: {supported_media_types}")

    if client_accept in supported_media_types:
        print("Selected representation: application/json")
    else:
        print("Response: 406 Not Acceptable")

    print("\nContent-Type describes the representation being sent.")
    print("Accept describes representations the client is willing to receive.")


# =============================================================================
# 16. API VERSIONING
# =============================================================================

def versioning_demo() -> None:
    section("16. API versioning")

    examples = [
        "/api/v1/products",
        "/api/v2/products",
    ]

    for endpoint in examples:
        print(endpoint)

    print(
        "\nVersioning is a compatibility strategy. It should not be treated "
        "as a substitute for careful backward-compatible API evolution."
    )

    print("\nPossible versioning approaches:")
    print("  - URI versioning")
    print("  - Header-based versioning")
    print("  - Media-type versioning")

    print("\nThe implementation in this study uses URI versioning for clarity.")


# =============================================================================
# 17. AUTHORIZATION
# =============================================================================

@dataclass(frozen=True)
class User:
    user_id: int
    role: str


class AuthorizationService:
    permissions = {
        "customer": {"GET_PRODUCT"},
        "admin": {
            "GET_PRODUCT",
            "CREATE_PRODUCT",
            "UPDATE_PRODUCT",
            "DELETE_PRODUCT",
        },
    }

    def can(self, user: User, permission: str) -> bool:
        return permission in self.permissions.get(user.role, set())


def authorization_demo() -> None:
    section("17. Authentication and authorization")

    authorization = AuthorizationService()

    customer = User(1, "customer")
    administrator = User(2, "admin")

    checks = [
        (customer, "GET_PRODUCT"),
        (customer, "DELETE_PRODUCT"),
        (administrator, "DELETE_PRODUCT"),
    ]

    for user, permission in checks:
        print(
            f"user={user.user_id}, role={user.role}, "
            f"permission={permission}, allowed={authorization.can(user, permission)}"
        )

    print(
        "\nAuthentication answers 'who are you?'. "
        "Authorization answers 'what are you allowed to do?'."
    )


# =============================================================================
# 18. RATE LIMITING
# =============================================================================

class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: Dict[str, Tuple[int, float]] = {}

    def allow(self, client_id: str) -> bool:
        now = time.monotonic()
        count, window_start = self.requests.get(client_id, (0, now))

        if now - window_start >= self.window_seconds:
            count = 0
            window_start = now

        if count >= self.limit:
            self.requests[client_id] = (count, window_start)
            return False

        count += 1
        self.requests[client_id] = (count, window_start)
        return True


def rate_limiting_demo() -> None:
    section("18. Rate limiting")

    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60)

    for attempt in range(1, 6):
        print(
            f"request {attempt}: "
            f"{'allowed' if limiter.allow('client-1') else '429 Too Many Requests'}"
        )

    print(
        "\nReal systems may use fixed windows, sliding windows, token buckets, "
        "leaky buckets, distributed counters, or gateway-level controls."
    )


# =============================================================================
# 19. ROUTING
# =============================================================================

RouteHandler = Callable[[HttpRequest, Dict[str, str]], HttpResponse]


class Router:
    """
    A small educational router.

    It demonstrates that an endpoint combines an HTTP method and URI pattern,
    rather than treating the URI alone as the operation.
    """

    def __init__(self) -> None:
        self.routes: List[
            Tuple[HttpMethod, re.Pattern[str], RouteHandler]
        ] = []

    def add(
        self,
        method: HttpMethod,
        pattern: str,
        handler: RouteHandler,
    ) -> None:
        self.routes.append((method, re.compile(pattern), handler))

    def dispatch(self, request: HttpRequest) -> HttpResponse:
        for method, pattern, handler in self.routes:
            if method != request.method:
                continue

            match = pattern.fullmatch(request.path)
            if match:
                return handler(request, match.groupdict())

        return HttpResponse(
            404,
            body={
                "error": {
                    "code": "ROUTE_NOT_FOUND",
                    "message": "No matching endpoint",
                }
            },
        )


def routing_demo() -> None:
    section("19. Routing")

    router = Router()

    def product_handler(
        request: HttpRequest,
        parameters: Dict[str, str],
    ) -> HttpResponse:
        return HttpResponse(
            200,
            body={
                "resource": "product",
                "id": int(parameters["id"]),
                "method": request.method.value,
            },
        )

    router.add(
        HttpMethod.GET,
        r"/api/v1/products/(?P<id>\d+)",
        product_handler,
    )

    request = HttpRequest(
        method=HttpMethod.GET,
        path="/api/v1/products/42",
    )

    response = router.dispatch(request)
    print(json.dumps(response.to_http_like_dict(), indent=2))


# =============================================================================
# 20. URI SAFETY AND INPUT VALIDATION
# =============================================================================

def input_security_demo() -> None:
    section("20. Input validation and security")

    unsafe_id = "../../etc/passwd"

    if not unsafe_id.isdigit():
        print(
            f"Rejected resource identifier: {unsafe_id!r} "
            "(expected a numeric identifier)"
        )

    dangerous_search = "<script>alert('x')</script>"

    # API validation should reject or safely encode inappropriate input.
    # The example intentionally does not execute or render the input.
    print(f"Received search value safely as data: {dangerous_search!r}")

    print("\nSecurity principles:")
    print("  - Validate input at trust boundaries.")
    print("  - Authorize every protected operation.")
    print("  - Never trust client-supplied identity or permissions.")
    print("  - Protect secrets and credentials.")
    print("  - Apply rate limits where abuse is possible.")
    print("  - Use TLS for sensitive traffic.")
    print("  - Avoid leaking stack traces and internal implementation details.")
    print("  - Validate resource ownership before modification or deletion.")


# =============================================================================
# 21. API OBSERVABILITY
# =============================================================================

@dataclass
class RequestMetrics:
    count: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0

    @property
    def average_latency_ms(self) -> float:
        return (
            self.total_latency_ms / self.count
            if self.count else 0.0
        )


class ApiMetrics:
    def __init__(self) -> None:
        self.by_endpoint: Dict[str, RequestMetrics] = defaultdict(RequestMetrics)

    def record(
        self,
        endpoint: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        metric = self.by_endpoint[endpoint]
        metric.count += 1
        metric.total_latency_ms += latency_ms

        if not success:
            metric.errors += 1


def observability_demo() -> None:
    section("21. Logging, metrics, and observability")

    metrics = ApiMetrics()

    simulated_requests = [
        ("/api/v1/products", 12.2, True),
        ("/api/v1/products", 8.4, True),
        ("/api/v1/products/101", 4.8, True),
        ("/api/v1/products/999", 3.1, False),
    ]

    for endpoint, latency, success in simulated_requests:
        metrics.record(endpoint, latency, success)

    for endpoint, metric in metrics.by_endpoint.items():
        print(
            endpoint,
            {
                "requests": metric.count,
                "errors": metric.errors,
                "average_latency_ms": round(metric.average_latency_ms, 2),
            },
        )

    print("\nUseful production signals include:")
    print("  - request count")
    print("  - latency distributions")
    print("  - error rates")
    print("  - status-code distributions")
    print("  - saturation")
    print("  - dependency failures")
    print("  - trace identifiers")


# =============================================================================
# 22. HATEOAS / HYPERMEDIA
# =============================================================================

def hypermedia_demo() -> None:
    section("22. Hypermedia and HATEOAS")

    representation = {
        "id": 101,
        "name": "Mechanical Keyboard",
        "_links": {
            "self": {"href": "/api/v1/products/101"},
            "reviews": {"href": "/api/v1/products/101/reviews"},
            "collection": {"href": "/api/v1/products"},
        },
    }

    print(json.dumps(representation, indent=2))

    print(
        "\nHypermedia can place navigational relationships in representations, "
        "allowing clients to discover related actions or resources."
    )


# =============================================================================
# 23. API DESIGN TRADE-OFFS
# =============================================================================

def tradeoff_demo() -> None:
    section("23. REST API design trade-offs")

    comparisons = [
        (
            "Nested URI",
            "/users/7/orders/22",
            "Expresses a relationship clearly",
            "Deep nesting can become difficult to maintain",
        ),
        (
            "Flat URI",
            "/orders/22",
            "Simple direct resource addressing",
            "Relationship must be represented elsewhere",
        ),
        (
            "Offset pagination",
            "page=10&limit=20",
            "Simple for clients",
            "Large offsets can become expensive",
        ),
        (
            "Cursor pagination",
            "cursor=abc123",
            "Better for changing or large datasets",
            "More complex client and server semantics",
        ),
    ]

    for name, example, advantage, limitation in comparisons:
        print(f"\n{name}")
        print(f"  Example: {example}")
        print(f"  Advantage: {advantage}")
        print(f"  Limitation: {limitation}")


# =============================================================================
# 24. TESTING
# =============================================================================

def testing_demo() -> None:
    section("24. API testing")

    repository = ProductRepository()
    api = ProductApi(repository)

    response = api.create_product({
        "name": "Test Product",
        "category": "test",
        "price": 100,
        "stock": 5,
    })

    assert response.status_code == 201
    assert response.body["data"]["name"] == "Test Product"

    product_id = response.body["data"]["id"]

    get_response = api.get_product(product_id)
    assert get_response.status_code == 200
    assert get_response.body["data"]["id"] == product_id

    patch_response = api.patch_product(
        product_id,
        {"stock": 3},
    )
    assert patch_response.status_code == 200
    assert patch_response.body["data"]["stock"] == 3

    missing_response = api.get_product(999999)
    assert missing_response.status_code == 404

    invalid_response = api.create_product({
        "name": "",
        "price": -1,
        "stock": -4,
    })
    assert invalid_response.status_code == 422

    delete_response = api.delete_product(product_id)
    assert delete_response.status_code == 204

    print("All executable API assertions passed.")


# =============================================================================
# 25. PERFORMANCE CONSIDERATIONS
# =============================================================================

def performance_demo() -> None:
    section("25. Performance considerations")

    repository = ProductRepository()

    for index in range(10_000):
        repository.create(
            name=f"Product {index}",
            category="electronics" if index % 2 == 0 else "other",
            price=float(index),
            stock=index % 100,
        )

    start = time.perf_counter()

    products = [
        product
        for product in repository.list()
        if product.category == "electronics"
        and product.price < 5000
    ]

    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"Matched products: {len(products)}")
    print(f"In-memory filtering time: {elapsed_ms:.3f} ms")

    print("\nProduction performance depends heavily on:")
    print("  - database indexes")
    print("  - query plans")
    print("  - network latency")
    print("  - serialization cost")
    print("  - payload size")
    print("  - caching")
    print("  - connection pooling")
    print("  - concurrency")
    print("  - downstream service latency")

    print(
        "\nAn O(n) Python list scan is useful pedagogically but should not "
        "automatically be treated as the production database strategy."
    )


# =============================================================================
# 26. COMPLETE API FLOW
# =============================================================================

def complete_flow_demo() -> None:
    section("26. Complete REST request lifecycle")

    flow = [
        "1. Client constructs an HTTP request.",
        "2. DNS and networking locate the service.",
        "3. TLS may establish an encrypted connection.",
        "4. A load balancer or gateway may receive the request.",
        "5. Authentication identifies the caller.",
        "6. Authorization determines whether the operation is allowed.",
        "7. Rate limiting and request validation may be applied.",
        "8. Routing selects the endpoint handler.",
        "9. Application logic reads or changes a resource.",
        "10. A database or another service may be contacted.",
        "11. The server creates a representation and status code.",
        "12. Cache headers and other response headers are added.",
        "13. The response returns through intermediary layers.",
        "14. The client interprets the response.",
        "15. Metrics, logs, and traces record the operation.",
    ]

    for item in flow:
        print(item)


# =============================================================================
# 27. FINAL STUDY CHECK
# =============================================================================

def study_check() -> None:
    section("27. Conceptual study check")

    questions = [
        (
            "What is a resource?",
            "A conceptual entity identified and manipulated through the API.",
        ),
        (
            "What is an endpoint?",
            "A method plus URI pattern through which a client interacts with a resource.",
        ),
        (
            "What does GET normally do?",
            "Retrieve a representation without requesting a state-changing operation.",
        ),
        (
            "What does POST normally do?",
            "Submit a representation for processing, often creating a subordinate resource.",
        ),
        (
            "What is statelessness?",
            "Each request carries the context necessary for independent processing.",
        ),
        (
            "What is idempotence?",
            "Repeating the same operation has the same intended resource-state effect.",
        ),
        (
            "Why is PATCH different from PUT?",
            "PATCH represents partial modification; PUT represents replacement.",
        ),
        (
            "Why use HTTP status codes?",
            "They communicate standardized high-level outcomes of requests.",
        ),
        (
            "Why validate API input?",
            "To protect correctness, security, data integrity, and predictable behavior.",
        ),
    ]

    for question, answer in questions:
        print(f"\nQ: {question}")
        print(f"A: {answer}")


# =============================================================================
# 28. MAIN PROGRAM
# =============================================================================

def main() -> None:
    fundamentals_demo()
    resource_demo()
    endpoint_design_demo()
    method_properties_demo()
    http_message_demo()
    status_code_demo()
    validation_demo()
    rest_service_demo()
    put_patch_demo()
    statelessness_demo()
    idempotence_demo()
    idempotency_key_demo()
    advanced_query_demo()
    caching_demo()
    content_negotiation_demo()
    versioning_demo()
    authorization_demo()
    rate_limiting_demo()
    routing_demo()
    input_security_demo()
    observability_demo()
    hypermedia_demo()
    tradeoff_demo()
    testing_demo()
    performance_demo()
    complete_flow_demo()
    study_check()


if __name__ == "__main__":
    main()
