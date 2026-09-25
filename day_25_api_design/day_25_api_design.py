"""
API Design: Versioning, Pagination, Filtering, and Error Handling
===================================================================

A self-contained study program covering REST-style API design from beginner
through advanced concepts.

The program models a small Product Catalog API entirely in memory. It
demonstrates:

- HTTP/API terminology
- Resources and representations
- API versioning
- URL and header based versioning concepts
- Pagination
- Offset and cursor pagination
- Filtering
- Sorting
- Validation
- Consistent error responses
- HTTP status codes
- Idempotency
- Content negotiation concepts
- Rate-limit metadata
- Security considerations
- Backward compatibility
- API evolution
- Repository/service/controller separation
- Testing
- Performance considerations
- Production-oriented design decisions

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import base64
import hashlib
import json
import math
import time


# ============================================================================
# 1. FUNDAMENTAL API TERMINOLOGY
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def pretty(value: Any) -> None:
    print(json.dumps(value, indent=2, default=str))


section("1. API FUNDAMENTALS")

print(
    """
An API is a defined interface through which one software component can
communicate with another.

In an HTTP API, common concepts include:

Resource:
    A domain object exposed by the API, such as /products/42.

Endpoint:
    A combination of an HTTP method and a resource URL.

Representation:
    A serialized form of a resource, commonly JSON.

Request:
    Information sent by a client to a server.

Response:
    Information returned by the server.

Common HTTP methods:
    GET     Retrieve information.
    POST    Create a resource or initiate an operation.
    PUT     Replace a resource.
    PATCH   Partially modify a resource.
    DELETE  Remove a resource.

A well-designed API should have predictable resource names, explicit
contracts, stable error formats, controlled evolution, and documented
behavior for edge cases.
"""
)


# ============================================================================
# 2. DOMAIN MODEL
# ============================================================================

@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    category: str
    price: float
    stock: int
    active: bool
    created_at: str


def create_product(
    product_id: int,
    name: str,
    category: str,
    price: float,
    stock: int,
    active: bool = True,
) -> Product:
    """Construct a product after domain-level validation."""
    if product_id <= 0:
        raise ValueError("product_id must be positive")

    if not name.strip():
        raise ValueError("name must not be empty")

    if not category.strip():
        raise ValueError("category must not be empty")

    if price < 0:
        raise ValueError("price must not be negative")

    if stock < 0:
        raise ValueError("stock must not be negative")

    return Product(
        product_id=product_id,
        name=name.strip(),
        category=category.strip().lower(),
        price=round(price, 2),
        stock=stock,
        active=active,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# 3. REPOSITORY
# ============================================================================

class ProductRepository:
    """
    Persistence abstraction.

    A real application could replace this implementation with PostgreSQL,
    MySQL, MongoDB, DynamoDB, or another data store without changing the
    API-facing service logic.
    """

    def __init__(self, products: Optional[Iterable[Product]] = None):
        self._products: Dict[int, Product] = {}

        for product in products or []:
            self._products[product.product_id] = product

    def list(self) -> List[Product]:
        return list(self._products.values())

    def get(self, product_id: int) -> Optional[Product]:
        return self._products.get(product_id)

    def create(self, product: Product) -> Product:
        if product.product_id in self._products:
            raise ValueError("Product already exists")

        self._products[product.product_id] = product
        return product

    def replace(self, product: Product) -> Product:
        if product.product_id not in self._products:
            raise KeyError("Product not found")

        self._products[product.product_id] = product
        return product

    def delete(self, product_id: int) -> bool:
        return self._products.pop(product_id, None) is not None


# ============================================================================
# 4. CONSISTENT API ERROR MODEL
# ============================================================================

@dataclass
class APIError:
    code: str
    message: str
    status: int
    details: Optional[Dict[str, Any]] = None

    def to_response(self, request_id: str) -> Dict[str, Any]:
        body = {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": request_id,
            }
        }

        if self.details:
            body["error"]["details"] = self.details

        return body


class APIException(Exception):
    """Application exception that maps cleanly to an API error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error = APIError(code, message, status, details)


# ============================================================================
# 5. HTTP STATUS CODE REFERENCE
# ============================================================================

section("2. HTTP STATUS CODES")

status_codes = {
    200: "OK - successful request",
    201: "Created - resource successfully created",
    204: "No Content - successful operation with no response body",
    400: "Bad Request - malformed or invalid request",
    401: "Unauthorized - authentication is required or invalid",
    403: "Forbidden - authenticated client lacks permission",
    404: "Not Found - resource does not exist",
    409: "Conflict - request conflicts with current state",
    412: "Precondition Failed - supplied precondition was not satisfied",
    422: "Unprocessable Content - syntactically valid but semantically invalid",
    429: "Too Many Requests - rate limit exceeded",
    500: "Internal Server Error",
    503: "Service Unavailable",
}

for code, meaning in status_codes.items():
    print(f"{code}: {meaning}")


# ============================================================================
# 6. PAGINATION
# ============================================================================

class Pagination:
    """
    Offset pagination.

    Example:
        page=2, page_size=10
        offset = (2 - 1) * 10 = 10

    Advantages:
        - Simple
        - Easy to understand
        - Works well for moderate result sets

    Disadvantages:
        - Large offsets can become expensive
        - Insertions/deletions can cause records to shift between pages
    """

    MAX_PAGE_SIZE = 100
    DEFAULT_PAGE_SIZE = 20

    @classmethod
    def normalize(
        cls,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[int, int]:
        if page < 1:
            raise APIException(
                "INVALID_PAGE",
                "page must be greater than or equal to 1",
                400,
            )

        if page_size < 1:
            raise APIException(
                "INVALID_PAGE_SIZE",
                "page_size must be greater than or equal to 1",
                400,
            )

        if page_size > cls.MAX_PAGE_SIZE:
            raise APIException(
                "PAGE_SIZE_TOO_LARGE",
                f"page_size cannot exceed {cls.MAX_PAGE_SIZE}",
                400,
            )

        return page, page_size

    @staticmethod
    def build_metadata(
        page: int,
        page_size: int,
        total_items: int,
    ) -> Dict[str, Any]:
        total_pages = math.ceil(total_items / page_size) if total_items else 0

        return {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_previous": page > 1 and total_pages > 0,
            "has_next": page < total_pages,
        }


# ============================================================================
# 7. CURSOR PAGINATION
# ============================================================================

class CursorPagination:
    """
    Cursor pagination avoids large OFFSET scans by using a stable position.

    This example encodes the last product ID.

    Real systems often use a compound cursor such as:
        (created_at, product_id)

    A cursor should be treated as an opaque token by API clients.
    """

    @staticmethod
    def encode(product_id: int) -> str:
        raw = str(product_id).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def decode(cursor: str) -> int:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = base64.urlsafe_b64decode(padded.encode("ascii")).decode(
                "utf-8"
            )
            product_id = int(value)

            if product_id < 0:
                raise ValueError

            return product_id
        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            raise APIException(
                "INVALID_CURSOR",
                "The supplied pagination cursor is invalid",
                400,
            )


# ============================================================================
# 8. FILTERING AND SORTING
# ============================================================================

@dataclass
class ProductFilter:
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_stock: Optional[int] = None
    active: Optional[bool] = None
    search: Optional[str] = None

    def validate(self) -> None:
        if self.min_price is not None and self.min_price < 0:
            raise APIException(
                "INVALID_MIN_PRICE",
                "min_price cannot be negative",
                400,
            )

        if self.max_price is not None and self.max_price < 0:
            raise APIException(
                "INVALID_MAX_PRICE",
                "max_price cannot be negative",
                400,
            )

        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise APIException(
                "INVALID_PRICE_RANGE",
                "min_price cannot exceed max_price",
                400,
            )

        if self.min_stock is not None and self.min_stock < 0:
            raise APIException(
                "INVALID_MIN_STOCK",
                "min_stock cannot be negative",
                400,
            )


ALLOWED_SORT_FIELDS = {
    "id": lambda p: p.product_id,
    "name": lambda p: p.name.lower(),
    "category": lambda p: p.category,
    "price": lambda p: p.price,
    "stock": lambda p: p.stock,
    "created_at": lambda p: p.created_at,
}


def filter_products(
    products: Sequence[Product],
    product_filter: ProductFilter,
) -> List[Product]:
    product_filter.validate()

    result = list(products)

    if product_filter.category is not None:
        category = product_filter.category.strip().lower()
        result = [p for p in result if p.category == category]

    if product_filter.min_price is not None:
        result = [
            p for p in result
            if p.price >= product_filter.min_price
        ]

    if product_filter.max_price is not None:
        result = [
            p for p in result
            if p.price <= product_filter.max_price
        ]

    if product_filter.min_stock is not None:
        result = [
            p for p in result
            if p.stock >= product_filter.min_stock
        ]

    if product_filter.active is not None:
        result = [
            p for p in result
            if p.active == product_filter.active
        ]

    if product_filter.search:
        term = product_filter.search.strip().lower()

        result = [
            p
            for p in result
            if term in p.name.lower()
            or term in p.category.lower()
        ]

    return result


def sort_products(
    products: Sequence[Product],
    sort_by: str = "id",
    descending: bool = False,
) -> List[Product]:
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise APIException(
            "INVALID_SORT_FIELD",
            f"Unsupported sort field: {sort_by}",
            400,
            {"allowed": sorted(ALLOWED_SORT_FIELDS)},
        )

    return sorted(
        products,
        key=ALLOWED_SORT_FIELDS[sort_by],
        reverse=descending,
    )


# ============================================================================
# 9. SERVICE LAYER
# ============================================================================

class ProductService:
    """
    Business logic layer.

    Keeping business rules out of the HTTP layer makes the application easier
    to test and makes it possible to reuse the same rules from other clients.
    """

    def __init__(self, repository: ProductRepository):
        self.repository = repository

    def get_product(self, product_id: int) -> Product:
        if product_id <= 0:
            raise APIException(
                "INVALID_PRODUCT_ID",
                "product_id must be positive",
                400,
            )

        product = self.repository.get(product_id)

        if product is None:
            raise APIException(
                "PRODUCT_NOT_FOUND",
                "The requested product does not exist",
                404,
                {"product_id": product_id},
            )

        return product

    def list_products(
        self,
        product_filter: ProductFilter,
        page: int,
        page_size: int,
        sort_by: str = "id",
        descending: bool = False,
    ) -> Dict[str, Any]:
        page, page_size = Pagination.normalize(page, page_size)

        products = filter_products(
            self.repository.list(),
            product_filter,
        )

        products = sort_products(
            products,
            sort_by=sort_by,
            descending=descending,
        )

        total_items = len(products)
        offset = (page - 1) * page_size
        page_items = products[offset: offset + page_size]

        return {
            "data": [asdict(product) for product in page_items],
            "pagination": Pagination.build_metadata(
                page,
                page_size,
                total_items,
            ),
            "sort": {
                "field": sort_by,
                "direction": "desc" if descending else "asc",
            },
        }

    def create_product(
        self,
        product_id: int,
        name: str,
        category: str,
        price: float,
        stock: int,
    ) -> Product:
        product = create_product(
            product_id=product_id,
            name=name,
            category=category,
            price=price,
            stock=stock,
        )

        try:
            return self.repository.create(product)
        except ValueError:
            raise APIException(
                "PRODUCT_ALREADY_EXISTS",
                "A product with this ID already exists",
                409,
                {"product_id": product_id},
            )


# ============================================================================
# 10. API VERSIONING
# ============================================================================

class APIVersion:
    """
    Version policy.

    Version 1:
        Exposes price as a numeric value.

    Version 2:
        Adds a computed display_price field and explicitly returns a stable
        representation structure.

    Versioning should be used when a change is incompatible with existing
    consumers.

    Common approaches:
        /api/v1/products
        /api/v2/products

        Accept: application/vnd.example.v2+json

        Header:
            API-Version: 2

    URL versioning is easy to discover. Header/media-type versioning keeps
    URLs cleaner but requires more sophisticated client behavior.
    """

    SUPPORTED = {"v1", "v2"}

    @classmethod
    def validate(cls, version: str) -> None:
        if version not in cls.SUPPORTED:
            raise APIException(
                "UNSUPPORTED_API_VERSION",
                f"API version '{version}' is not supported",
                400,
                {"supported_versions": sorted(cls.SUPPORTED)},
            )


def serialize_product(product: Product, version: str) -> Dict[str, Any]:
    APIVersion.validate(version)

    data = asdict(product)

    if version == "v1":
        return {
            "id": data["product_id"],
            "name": data["name"],
            "category": data["category"],
            "price": data["price"],
            "stock": data["stock"],
            "active": data["active"],
        }

    # v2 keeps existing core fields while introducing a structured field.
    return {
        "id": data["product_id"],
        "name": data["name"],
        "category": data["category"],
        "pricing": {
            "amount": data["price"],
            "currency": "USD",
            "display": f"${data['price']:.2f}",
        },
        "inventory": {
            "stock": data["stock"],
            "available": data["stock"] > 0,
        },
        "active": data["active"],
        "created_at": data["created_at"],
    }


# ============================================================================
# 11. IDEMPOTENCY
# ============================================================================

class IdempotencyStore:
    """
    Simplified in-memory idempotency store.

    Idempotency is particularly important for operations where a client might
    retry a request after a network timeout.

    A real production implementation would normally use durable storage and
    would associate a key with the authenticated client and request payload.
    """

    def __init__(self):
        self._responses: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._responses.get(key)

    def save(self, key: str, response: Dict[str, Any]) -> None:
        self._responses[key] = response


# ============================================================================
# 12. REQUEST VALIDATION
# ============================================================================

def parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes"}:
            return True

        if normalized in {"false", "0", "no"}:
            return False

    raise APIException(
        "INVALID_BOOLEAN",
        f"{field_name} must be a boolean value",
        400,
    )


def parse_non_negative_float(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise APIException(
            "INVALID_NUMBER",
            f"{field_name} must be numeric",
            400,
        )

    if not math.isfinite(parsed):
        raise APIException(
            "INVALID_NUMBER",
            f"{field_name} must be finite",
            400,
        )

    if parsed < 0:
        raise APIException(
            "NEGATIVE_VALUE",
            f"{field_name} cannot be negative",
            400,
        )

    return parsed


# ============================================================================
# 13. CONTROLLER-LIKE API SIMULATION
# ============================================================================

class ProductAPI:
    """
    HTTP-independent controller simulation.

    Each method returns:
        status code
        response headers
        JSON-like response body
    """

    def __init__(self, service: ProductService):
        self.service = service
        self.idempotency = IdempotencyStore()

    @staticmethod
    def _request_id() -> str:
        seed = f"{time.time_ns()}-{id(object())}".encode()
        return hashlib.sha256(seed).hexdigest()[:16]

    def list_products(
        self,
        version: str = "v1",
        page: int = 1,
        page_size: int = 5,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_stock: Optional[int] = None,
        active: Optional[bool] = None,
        search: Optional[str] = None,
        sort_by: str = "id",
        descending: bool = False,
    ) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        request_id = self._request_id()

        try:
            APIVersion.validate(version)

            product_filter = ProductFilter(
                category=category,
                min_price=min_price,
                max_price=max_price,
                min_stock=min_stock,
                active=active,
                search=search,
            )

            result = self.service.list_products(
                product_filter=product_filter,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                descending=descending,
            )

            result["data"] = [
                serialize_product(
                    self.service.get_product(item["product_id"]),
                    version,
                )
                for item in result["data"]
            ]

            headers = {
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
                "API-Version": version,
            }

            return 200, headers, result

        except APIException as exc:
            return (
                exc.error.status,
                {
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                },
                exc.error.to_response(request_id),
            )

    def get_product(
        self,
        product_id: int,
        version: str = "v1",
    ) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        request_id = self._request_id()

        try:
            APIVersion.validate(version)

            product = self.service.get_product(product_id)

            return (
                200,
                {
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                    "API-Version": version,
                },
                {
                    "data": serialize_product(product, version),
                },
            )

        except APIException as exc:
            return (
                exc.error.status,
                {
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                },
                exc.error.to_response(request_id),
            )

    def create_product(
        self,
        payload: Dict[str, Any],
        version: str = "v1",
        idempotency_key: Optional[str] = None,
    ) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        request_id = self._request_id()

        try:
            APIVersion.validate(version)

            if idempotency_key:
                previous = self.idempotency.get(idempotency_key)

                if previous is not None:
                    return (
                        previous["status"],
                        previous["headers"],
                        previous["body"],
                    )

            required = {
                "id",
                "name",
                "category",
                "price",
                "stock",
            }

            missing = sorted(required - payload.keys())

            if missing:
                raise APIException(
                    "VALIDATION_ERROR",
                    "Required fields are missing",
                    422,
                    {"missing_fields": missing},
                )

            try:
                product_id = int(payload["id"])
                stock = int(payload["stock"])
            except (TypeError, ValueError):
                raise APIException(
                    "INVALID_INTEGER",
                    "id and stock must be integers",
                    422,
                )

            price = parse_non_negative_float(
                payload["price"],
                "price",
            )

            product = self.service.create_product(
                product_id=product_id,
                name=str(payload["name"]),
                category=str(payload["category"]),
                price=price,
                stock=stock,
            )

            response = {
                "status": 201,
                "headers": {
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                    "API-Version": version,
                    "Location": f"/api/{version}/products/{product.product_id}",
                },
                "body": {
                    "data": serialize_product(product, version),
                },
            }

            if idempotency_key:
                self.idempotency.save(idempotency_key, response)

            return (
                response["status"],
                response["headers"],
                response["body"],
            )

        except APIException as exc:
            return (
                exc.error.status,
                {
                    "Content-Type": "application/json",
                    "X-Request-ID": request_id,
                },
                exc.error.to_response(request_id),
            )


# ============================================================================
# 14. CURSOR PAGINATION SERVICE
# ============================================================================

def cursor_page(
    products: Sequence[Product],
    limit: int,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cursor pagination over ascending product IDs.

    The cursor is intentionally opaque to clients.
    """
    if limit < 1 or limit > 100:
        raise APIException(
            "INVALID_LIMIT",
            "limit must be between 1 and 100",
            400,
        )

    ordered = sorted(products, key=lambda product: product.product_id)

    start_index = 0

    if cursor is not None:
        last_id = CursorPagination.decode(cursor)

        for index, product in enumerate(ordered):
            if product.product_id > last_id:
                start_index = index
                break
        else:
            start_index = len(ordered)

    selected = ordered[start_index:start_index + limit]
    has_more = start_index + limit < len(ordered)

    next_cursor = None

    if selected and has_more:
        next_cursor = CursorPagination.encode(
            selected[-1].product_id
        )

    return {
        "data": [asdict(product) for product in selected],
        "pagination": {
            "limit": limit,
            "next_cursor": next_cursor,
            "has_more": has_more,
        },
    }


# ============================================================================
# 15. SAMPLE DATA
# ============================================================================

products = [
    create_product(1, "Laptop Pro", "electronics", 1499.99, 12),
    create_product(2, "Wireless Mouse", "electronics", 29.99, 80),
    create_product(3, "Mechanical Keyboard", "electronics", 119.00, 35),
    create_product(4, "Office Chair", "furniture", 299.50, 17),
    create_product(5, "Standing Desk", "furniture", 499.00, 8),
    create_product(6, "Notebook", "stationery", 7.99, 250),
    create_product(7, "Pen Set", "stationery", 12.50, 120),
    create_product(8, "Monitor", "electronics", 349.99, 20),
    create_product(9, "Desk Lamp", "furniture", 45.00, 40),
    create_product(10, "USB Hub", "electronics", 39.99, 55),
    create_product(11, "Webcam", "electronics", 89.99, 28),
    create_product(12, "Bookshelf", "furniture", 180.00, 4),
]

repository = ProductRepository(products)
service = ProductService(repository)
api = ProductAPI(service)


# ============================================================================
# 16. BASIC API EXAMPLE
# ============================================================================

section("3. BASIC GET REQUEST")

status, headers, body = api.get_product(1, version="v1")

print("HTTP Status:", status)
print("Headers:")
pretty(headers)
print("Body:")
pretty(body)


# ============================================================================
# 17. VERSION 2
# ============================================================================

section("4. API VERSIONING")

status, headers, body = api.get_product(1, version="v2")

print("HTTP Status:", status)
print("Body:")
pretty(body)

print(
    """
Versioning is a contract-management mechanism.

A version should not be introduced for every small implementation change.
It becomes useful when the response/request contract changes in a way that
existing clients cannot safely handle.

Compatible changes can often be made without a new version:
    - Adding optional response metadata
    - Adding a new endpoint
    - Adding optional request fields when old clients remain valid

Potentially breaking changes:
    - Renaming a response field
    - Removing a response field
    - Changing a field's type
    - Changing the meaning of an existing field
    - Making an optional field required
"""
)


# ============================================================================
# 18. FILTERING
# ============================================================================

section("5. FILTERING")

status, headers, body = api.list_products(
    version="v1",
    page=1,
    page_size=10,
    category="electronics",
    min_price=50,
    max_price=500,
    min_stock=10,
    active=True,
    search="",
    sort_by="price",
)

print("HTTP Status:", status)
pretty(body)


# ============================================================================
# 19. PAGINATION
# ============================================================================

section("6. OFFSET PAGINATION")

for page in (1, 2, 3):
    status, _, body = api.list_products(
        version="v1",
        page=page,
        page_size=4,
        sort_by="id",
    )

    print(f"\nPage {page}, HTTP {status}")
    print(
        "IDs:",
        [
            item["id"]
            for item in body.get("data", [])
        ],
    )
    pretty(body.get("pagination", {}))


# ============================================================================
# 20. CURSOR PAGINATION
# ============================================================================

section("7. CURSOR PAGINATION")

cursor = None

for iteration in range(4):
    try:
        result = cursor_page(
            repository.list(),
            limit=4,
            cursor=cursor,
        )

        print(f"\nCursor request {iteration + 1}")
        print(
            "IDs:",
            [
                item["product_id"]
                for item in result["data"]
            ],
        )

        cursor = result["pagination"]["next_cursor"]

        print("Next cursor:", cursor)

        if not result["pagination"]["has_more"]:
            break

    except APIException as exc:
        pretty(exc.error.to_response("cursor-demo"))


# ============================================================================
# 21. ERROR HANDLING
# ============================================================================

section("8. ERROR HANDLING")

error_examples = [
    ("Missing product", lambda: api.get_product(9999)),
    (
        "Invalid page",
        lambda: api.list_products(page=0),
    ),
    (
        "Page too large",
        lambda: api.list_products(page_size=1000),
    ),
    (
        "Invalid filter range",
        lambda: api.list_products(
            min_price=500,
            max_price=100,
        ),
    ),
    (
        "Invalid version",
        lambda: api.get_product(1, version="v99"),
    ),
    (
        "Invalid sort",
        lambda: api.list_products(sort_by="secret_field"),
    ),
]

for name, operation in error_examples:
    status, _, body = operation()

    print(f"\n{name}")
    print("HTTP Status:", status)
    pretty(body)


# ============================================================================
# 22. VALIDATION AND CREATE
# ============================================================================

section("9. VALIDATION")

invalid_payloads = [
    {
        "id": 20,
        "name": "",
        "category": "electronics",
        "price": 10,
        "stock": 1,
    },
    {
        "id": 21,
        "name": "Invalid",
        "category": "electronics",
        "price": -10,
        "stock": 1,
    },
    {
        "id": 22,
        "name": "Missing Category",
        "price": 10,
        "stock": 1,
    },
]

for payload in invalid_payloads:
    status, _, body = api.create_product(payload)

    print("Payload:")
    pretty(payload)
    print("Status:", status)
    pretty(body)


# ============================================================================
# 23. IDEMPOTENCY
# ============================================================================

section("10. IDEMPOTENT RETRIES")

payload = {
    "id": 20,
    "name": "API Design Handbook",
    "category": "books",
    "price": 49.99,
    "stock": 10,
}

first_status, first_headers, first_body = api.create_product(
    payload,
    idempotency_key="client-request-001",
)

second_status, second_headers, second_body = api.create_product(
    payload,
    idempotency_key="client-request-001",
)

print("First status:", first_status)
pretty(first_body)

print("\nSecond status using same idempotency key:", second_status)
pretty(second_body)

print(
    """
A retry-safe create operation prevents a network timeout from causing the
client to accidentally create duplicate resources.

The server should validate that a reused idempotency key refers to the same
logical request. Production systems generally persist these records and
scope them to the authenticated client.
"""
)


# ============================================================================
# 24. SECURITY CONSIDERATIONS
# ============================================================================

section("11. SECURITY CONSIDERATIONS")

security_principles = [
    "Authenticate clients before protected operations.",
    "Authorize every protected resource and operation.",
    "Validate and constrain all client-controlled input.",
    "Never expose secrets, passwords, tokens, or internal stack traces.",
    "Use HTTPS in production.",
    "Apply rate limiting to protect availability.",
    "Use parameterized database queries.",
    "Limit maximum page sizes.",
    "Allow-list sortable and filterable fields.",
    "Avoid exposing internal database identifiers when unnecessary.",
    "Log request IDs and security events without logging secrets.",
    "Use appropriate CORS policy for browser clients.",
    "Apply output encoding and content-type controls.",
]

for number, principle in enumerate(security_principles, 1):
    print(f"{number}. {principle}")


# ============================================================================
# 25. PERFORMANCE
# ============================================================================

section("12. PERFORMANCE CONSIDERATIONS")

performance_notes = {
    "Filtering": (
        "In-memory filtering is O(n). Database indexes can reduce the "
        "amount of data scanned."
    ),
    "Sorting": (
        "General sorting is typically O(n log n). Database indexes can "
        "sometimes avoid a full sort."
    ),
    "Offset pagination": (
        "Large offsets can become expensive because the database may scan "
        "and discard many rows."
    ),
    "Cursor pagination": (
        "A properly indexed cursor can provide efficient traversal for "
        "large datasets."
    ),
    "Maximum page size": (
        "Limits protect memory, bandwidth, database load, and response time."
    ),
    "Projection": (
        "Returning only requested fields can reduce serialization and "
        "network costs."
    ),
}

for concept, explanation in performance_notes.items():
    print(f"\n{concept}: {explanation}")


# ============================================================================
# 26. API DESIGN COMPARISON
# ============================================================================

section("13. IMPORTANT DESIGN COMPARISONS")

comparisons = [
    (
        "Offset pagination",
        "Simple page numbers",
        "Large datasets and frequently changing data can be problematic",
    ),
    (
        "Cursor pagination",
        "Stable traversal of large result sets",
        "Less intuitive and cursors must be treated as opaque",
    ),
    (
        "URL versioning",
        "Highly visible and easy to route",
        "URLs contain version information",
    ),
    (
        "Header versioning",
        "Cleaner resource URLs",
        "Less discoverable and more complex for some clients",
    ),
    (
        "PUT",
        "Full replacement semantics",
        "Clients generally need to provide the complete representation",
    ),
    (
        "PATCH",
        "Partial modification",
        "Requires carefully defined patch semantics",
    ),
    (
        "Generic errors",
        "Simple implementation",
        "Harder for clients to automate recovery",
    ),
    (
        "Structured errors",
        "Machine-readable and actionable",
        "Requires stable error-code contracts",
    ),
]

for approach, benefit, tradeoff in comparisons:
    print(f"\n{approach}")
    print("  Useful for:", benefit)
    print("  Trade-off:", tradeoff)


# ============================================================================
# 27. COMMON MISTAKES
# ============================================================================

section("14. COMMON API DESIGN MISTAKES")

mistakes = [
    "Returning HTTP 200 for every failure.",
    "Putting sensitive information in URLs.",
    "Allowing unlimited page sizes.",
    "Accepting arbitrary database field names for sorting.",
    "Changing field meanings without versioning or migration planning.",
    "Returning inconsistent error shapes from different endpoints.",
    "Leaking database exceptions to clients.",
    "Ignoring concurrent changes during pagination.",
    "Using offset pagination for extremely large, frequently changing datasets.",
    "Creating a new API version for every minor feature.",
    "Removing fields without considering existing consumers.",
    "Failing to document validation constraints.",
    "Not providing request IDs for production troubleshooting.",
    "Treating API documentation as separate from the actual contract.",
]

for mistake in mistakes:
    print("-", mistake)


# ============================================================================
# 28. ADVANCED CONCEPTS
# ============================================================================

section("15. ADVANCED API DESIGN CONCEPTS")

advanced_topics = {
    "Backward compatibility": (
        "Existing valid clients should continue to operate after compatible "
        "server changes."
    ),
    "Contract stability": (
        "Field names, types, meanings, status codes, and error codes should "
        "not change unexpectedly."
    ),
    "Conditional requests": (
        "ETag and If-Match/If-None-Match can reduce bandwidth and prevent "
        "lost updates."
    ),
    "Optimistic concurrency": (
        "Clients provide a version or ETag and the server rejects updates "
        "when the resource changed since it was read."
    ),
    "Rate limiting": (
        "Controls request volume and protects system capacity."
    ),
    "Observability": (
        "Request IDs, structured logs, metrics, and traces make failures "
        "diagnosable."
    ),
    "Caching": (
        "HTTP cache directives and application caches can reduce repeated "
        "work when freshness rules permit it."
    ),
    "Content negotiation": (
        "Clients and servers can negotiate representation formats using "
        "headers such as Accept and Content-Type."
    ),
    "Idempotency": (
        "Repeated execution of an operation can be made safe for retry "
        "scenarios."
    ),
}

for topic, explanation in advanced_topics.items():
    print(f"\n{topic}:")
    print(explanation)


# ============================================================================
# 29. MINI TEST SUITE
# ============================================================================

section("16. EXECUTABLE TESTS")


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}: expected {expected!r}, got {actual!r}"
        )


def test_get_existing_product() -> None:
    status, _, body = api.get_product(1)
    assert_equal(status, 200, "Existing product should return 200")
    assert_equal(body["data"]["id"], 1, "Product ID should match")


def test_get_missing_product() -> None:
    status, _, body = api.get_product(999999)
    assert_equal(status, 404, "Missing product should return 404")
    assert_equal(
        body["error"]["code"],
        "PRODUCT_NOT_FOUND",
        "Error code should identify missing product",
    )


def test_pagination() -> None:
    status, _, body = api.list_products(
        page=2,
        page_size=3,
    )

    assert_equal(status, 200, "Pagination should succeed")
    assert_equal(
        body["pagination"]["page"],
        2,
        "Returned page should be correct",
    )
    assert_equal(
        len(body["data"]),
        3,
        "Page should contain three records",
    )


def test_filtering() -> None:
    status, _, body = api.list_products(
        category="electronics",
        min_price=100,
    )

    assert_equal(status, 200, "Filtering should succeed")

    for item in body["data"]:
        assert item["category"] == "electronics"
        assert item["price"] >= 100


def test_versioning() -> None:
    status_v1, _, body_v1 = api.get_product(1, "v1")
    status_v2, _, body_v2 = api.get_product(1, "v2")

    assert_equal(status_v1, 200, "v1 should work")
    assert_equal(status_v2, 200, "v2 should work")

    assert "price" in body_v1["data"]
    assert "pricing" in body_v2["data"]


def test_cursor_pagination() -> None:
    first = cursor_page(repository.list(), limit=3)

    assert_equal(
        len(first["data"]),
        3,
        "First cursor page should contain three items",
    )

    second = cursor_page(
        repository.list(),
        limit=3,
        cursor=first["pagination"]["next_cursor"],
    )

    assert second["data"][0]["product_id"] > first["data"][-1]["product_id"]


tests = [
    test_get_existing_product,
    test_get_missing_product,
    test_pagination,
    test_filtering,
    test_versioning,
    test_cursor_pagination,
]

passed = 0

for test in tests:
    test()
    print(f"PASS: {test.__name__}")
    passed += 1

print(f"\n{passed}/{len(tests)} tests passed.")


# ============================================================================
# 30. FINAL DESIGN CHECKLIST
# ============================================================================

section("17. API DESIGN CHECKLIST")

checklist = [
    "Resources have stable, predictable representations.",
    "HTTP methods have appropriate semantics.",
    "Status codes communicate success and failure accurately.",
    "Validation happens at the API boundary and domain layer.",
    "Errors have stable machine-readable codes.",
    "Request IDs support troubleshooting.",
    "Pagination has explicit limits.",
    "Filtering and sorting use allow-lists.",
    "Large collections have an efficient pagination strategy.",
    "Breaking changes have an explicit versioning strategy.",
    "Existing clients are considered before contract changes.",
    "Retries are safe where operations can be repeated.",
    "Authentication and authorization are separated from business logic.",
    "Sensitive information is not exposed in errors.",
    "Performance constraints are considered before production deployment.",
    "Observability is part of the API design.",
]

for item in checklist:
    print("[x]", item)


if __name__ == "__main__":
    print(
        "\nAPI design study program completed successfully. "
        "All demonstrations above execute without external packages."
    )
