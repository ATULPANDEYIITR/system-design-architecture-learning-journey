/*
 * API Design: Versioning, Pagination, Filtering, and Error Handling
 * =================================================================
 *
 * This file complements the Python study implementation by focusing on
 * JavaScript's strengths:
 *
 * - URL and query-string handling
 * - Objects and serialization
 * - asynchronous API-style operations
 * - Promise-based error handling
 * - functional filtering and transformation
 * - browser/server-compatible URL APIs
 * - HTTP-style response objects
 * - cursor pagination
 * - validation
 * - idempotency
 * - concurrency and retry concepts
 *
 * Run with:
 *     node api_design.js
 *
 * No external packages are required.
 */

"use strict";

// ============================================================================
// 1. BASIC HTTP/API CONCEPTS
// ============================================================================

console.log("=".repeat(78));
console.log("1. API FUNDAMENTALS");
console.log("=".repeat(78));

const httpMethods = {
    GET: "Retrieve a resource or collection.",
    POST: "Create a resource or initiate an operation.",
    PUT: "Replace an existing resource.",
    PATCH: "Partially modify an existing resource.",
    DELETE: "Remove a resource."
};

for (const [method, meaning] of Object.entries(httpMethods)) {
    console.log(`${method.padEnd(7)} ${meaning}`);
}


// ============================================================================
// 2. DATA MODEL
// ============================================================================

class Product {
    constructor({
        id,
        name,
        category,
        price,
        stock,
        active = true,
        createdAt = new Date().toISOString()
    }) {
        if (!Number.isInteger(id) || id <= 0) {
            throw new APIError(
                "INVALID_PRODUCT_ID",
                "id must be a positive integer",
                422
            );
        }

        if (typeof name !== "string" || name.trim() === "") {
            throw new APIError(
                "INVALID_NAME",
                "name must be a non-empty string",
                422
            );
        }

        if (typeof category !== "string" || category.trim() === "") {
            throw new APIError(
                "INVALID_CATEGORY",
                "category must be a non-empty string",
                422
            );
        }

        if (!Number.isFinite(price) || price < 0) {
            throw new APIError(
                "INVALID_PRICE",
                "price must be a finite non-negative number",
                422
            );
        }

        if (!Number.isInteger(stock) || stock < 0) {
            throw new APIError(
                "INVALID_STOCK",
                "stock must be a non-negative integer",
                422
            );
        }

        this.id = id;
        this.name = name.trim();
        this.category = category.trim().toLowerCase();
        this.price = Number(price.toFixed(2));
        this.stock = stock;
        this.active = Boolean(active);
        this.createdAt = createdAt;
    }

    toV1() {
        return {
            id: this.id,
            name: this.name,
            category: this.category,
            price: this.price,
            stock: this.stock,
            active: this.active
        };
    }

    toV2() {
        return {
            id: this.id,
            name: this.name,
            category: this.category,
            pricing: {
                amount: this.price,
                currency: "USD",
                display: `$${this.price.toFixed(2)}`
            },
            inventory: {
                stock: this.stock,
                available: this.stock > 0
            },
            active: this.active,
            createdAt: this.createdAt
        };
    }
}


// ============================================================================
// 3. API ERROR MODEL
// ============================================================================

class APIError extends Error {
    constructor(code, message, status, details = undefined) {
        super(message);

        this.name = "APIError";
        this.code = code;
        this.status = status;
        this.details = details;
    }

    toJSON(requestId) {
        const error = {
            code: this.code,
            message: this.message,
            requestId
        };

        if (this.details !== undefined) {
            error.details = this.details;
        }

        return {
            error
        };
    }
}


// ============================================================================
// 4. REPOSITORY
// ============================================================================

class ProductRepository {
    constructor(products = []) {
        this.products = new Map();

        for (const product of products) {
            this.products.set(product.id, product);
        }
    }

    async list() {
        // An async repository resembles the behavior of a real database call.
        return Array.from(this.products.values());
    }

    async get(id) {
        return this.products.get(id) ?? null;
    }

    async create(product) {
        if (this.products.has(product.id)) {
            throw new APIError(
                "PRODUCT_ALREADY_EXISTS",
                "A product with this ID already exists",
                409,
                { id: product.id }
            );
        }

        this.products.set(product.id, product);
        return product;
    }
}


// ============================================================================
// 5. SERVICE LAYER
// ============================================================================

class ProductService {
    constructor(repository) {
        this.repository = repository;
    }

    async getProduct(id) {
        if (!Number.isInteger(id) || id <= 0) {
            throw new APIError(
                "INVALID_PRODUCT_ID",
                "id must be a positive integer",
                400
            );
        }

        const product = await this.repository.get(id);

        if (!product) {
            throw new APIError(
                "PRODUCT_NOT_FOUND",
                "The requested product does not exist",
                404,
                { id }
            );
        }

        return product;
    }

    async createProduct(input) {
        if (!input || typeof input !== "object") {
            throw new APIError(
                "INVALID_BODY",
                "Request body must be a JSON object",
                400
            );
        }

        const requiredFields = [
            "id",
            "name",
            "category",
            "price",
            "stock"
        ];

        const missingFields = requiredFields.filter(
            field => !(field in input)
        );

        if (missingFields.length > 0) {
            throw new APIError(
                "VALIDATION_ERROR",
                "Required fields are missing",
                422,
                { missingFields }
            );
        }

        const product = new Product(input);

        return this.repository.create(product);
    }

    async listProducts(options = {}) {
        const {
            page = 1,
            pageSize = 10,
            category,
            minPrice,
            maxPrice,
            minStock,
            active,
            search,
            sortBy = "id",
            descending = false
        } = options;

        validatePage(page, pageSize);

        const allowedSortFields = new Set([
            "id",
            "name",
            "category",
            "price",
            "stock",
            "createdAt"
        ]);

        if (!allowedSortFields.has(sortBy)) {
            throw new APIError(
                "INVALID_SORT_FIELD",
                `Unsupported sort field: ${sortBy}`,
                400,
                {
                    allowed: Array.from(allowedSortFields)
                }
            );
        }

        if (
            minPrice !== undefined &&
            (!Number.isFinite(Number(minPrice)) || Number(minPrice) < 0)
        ) {
            throw new APIError(
                "INVALID_MIN_PRICE",
                "minPrice must be a non-negative number",
                400
            );
        }

        if (
            maxPrice !== undefined &&
            (!Number.isFinite(Number(maxPrice)) || Number(maxPrice) < 0)
        ) {
            throw new APIError(
                "INVALID_MAX_PRICE",
                "maxPrice must be a non-negative number",
                400
            );
        }

        if (
            minPrice !== undefined &&
            maxPrice !== undefined &&
            Number(minPrice) > Number(maxPrice)
        ) {
            throw new APIError(
                "INVALID_PRICE_RANGE",
                "minPrice cannot exceed maxPrice",
                400
            );
        }

        let products = await this.repository.list();

        // Filtering is intentionally expressed as separate predicates.
        // In a real database-backed service these conditions should usually
        // be translated into indexed database queries rather than filtering
        // the entire table in application memory.
        if (category !== undefined) {
            products = products.filter(
                product => product.category === String(category).toLowerCase()
            );
        }

        if (minPrice !== undefined) {
            products = products.filter(
                product => product.price >= Number(minPrice)
            );
        }

        if (maxPrice !== undefined) {
            products = products.filter(
                product => product.price <= Number(maxPrice)
            );
        }

        if (minStock !== undefined) {
            if (!Number.isInteger(Number(minStock)) || Number(minStock) < 0) {
                throw new APIError(
                    "INVALID_MIN_STOCK",
                    "minStock must be a non-negative integer",
                    400
                );
            }

            products = products.filter(
                product => product.stock >= Number(minStock)
            );
        }

        if (active !== undefined) {
            products = products.filter(
                product => product.active === Boolean(active)
            );
        }

        if (search !== undefined && String(search).trim() !== "") {
            const term = String(search).trim().toLowerCase();

            products = products.filter(product =>
                product.name.toLowerCase().includes(term) ||
                product.category.toLowerCase().includes(term)
            );
        }

        const getSortValue = product => product[sortBy];

        products.sort((a, b) => {
            const left = getSortValue(a);
            const right = getSortValue(b);

            if (left < right) {
                return descending ? 1 : -1;
            }

            if (left > right) {
                return descending ? -1 : 1;
            }

            // A stable secondary key prevents ambiguous ordering when two
            // products have identical primary sort values.
            return a.id - b.id;
        });

        const totalItems = products.length;
        const offset = (page - 1) * pageSize;

        const data = products.slice(
            offset,
            offset + pageSize
        );

        const totalPages = totalItems === 0
            ? 0
            : Math.ceil(totalItems / pageSize);

        return {
            data,
            pagination: {
                page,
                pageSize,
                totalItems,
                totalPages,
                hasPrevious: page > 1 && totalPages > 0,
                hasNext: page < totalPages
            },
            sort: {
                field: sortBy,
                direction: descending ? "desc" : "asc"
            }
        };
    }
}


// ============================================================================
// 6. VALIDATION HELPERS
// ============================================================================

function validatePage(page, pageSize) {
    if (!Number.isInteger(page) || page < 1) {
        throw new APIError(
            "INVALID_PAGE",
            "page must be a positive integer",
            400
        );
    }

    if (!Number.isInteger(pageSize) || pageSize < 1) {
        throw new APIError(
            "INVALID_PAGE_SIZE",
            "pageSize must be a positive integer",
            400
        );
    }

    if (pageSize > 100) {
        throw new APIError(
            "PAGE_SIZE_TOO_LARGE",
            "pageSize cannot exceed 100",
            400
        );
    }
}


// ============================================================================
// 7. VERSION NEGOTIATION
// ============================================================================

function validateVersion(version) {
    const supportedVersions = new Set(["v1", "v2"]);

    if (!supportedVersions.has(version)) {
        throw new APIError(
            "UNSUPPORTED_API_VERSION",
            `API version '${version}' is not supported`,
            400,
            {
                supportedVersions: Array.from(supportedVersions)
            }
        );
    }
}

function serializeProduct(product, version) {
    validateVersion(version);

    if (version === "v1") {
        return product.toV1();
    }

    return product.toV2();
}


// ============================================================================
// 8. REQUEST ID GENERATION
// ============================================================================

function createRequestId() {
    const randomPart = Math.random()
        .toString(36)
        .slice(2, 12);

    return `${Date.now().toString(36)}-${randomPart}`;
}


// ============================================================================
// 9. API CONTROLLER
// ============================================================================

class ProductAPI {
    constructor(service) {
        this.service = service;
        this.idempotencyStore = new Map();
    }

    async getProduct(id, version = "v1") {
        const requestId = createRequestId();

        try {
            validateVersion(version);

            const product = await this.service.getProduct(id);

            return {
                status: 200,
                headers: {
                    "Content-Type": "application/json",
                    "X-Request-ID": requestId,
                    "API-Version": version
                },
                body: {
                    data: serializeProduct(product, version)
                }
            };
        } catch (error) {
            return this.handleError(error, requestId);
        }
    }

    async listProducts(options = {}) {
        const requestId = createRequestId();
        const version = options.version ?? "v1";

        try {
            validateVersion(version);

            const result = await this.service.listProducts(options);

            return {
                status: 200,
                headers: {
                    "Content-Type": "application/json",
                    "X-Request-ID": requestId,
                    "API-Version": version
                },
                body: {
                    ...result,
                    data: result.data.map(
                        product => serializeProduct(product, version)
                    )
                }
            };
        } catch (error) {
            return this.handleError(error, requestId);
        }
    }

    async createProduct(input, {
        version = "v1",
        idempotencyKey
    } = {}) {
        const requestId = createRequestId();

        try {
            validateVersion(version);

            if (idempotencyKey) {
                const previous = this.idempotencyStore.get(idempotencyKey);

                if (previous) {
                    return previous;
                }
            }

            const product = await this.service.createProduct(input);

            const response = {
                status: 201,
                headers: {
                    "Content-Type": "application/json",
                    "X-Request-ID": requestId,
                    "API-Version": version,
                    "Location":
                        `/api/${version}/products/${product.id}`
                },
                body: {
                    data: serializeProduct(product, version)
                }
            };

            if (idempotencyKey) {
                this.idempotencyStore.set(
                    idempotencyKey,
                    response
                );
            }

            return response;
        } catch (error) {
            return this.handleError(error, requestId);
        }
    }

    handleError(error, requestId) {
        if (error instanceof APIError) {
            return {
                status: error.status,
                headers: {
                    "Content-Type": "application/json",
                    "X-Request-ID": requestId
                },
                body: error.toJSON(requestId)
            };
        }

        // Internal errors should not expose implementation details.
        return {
            status: 500,
            headers: {
                "Content-Type": "application/json",
                "X-Request-ID": requestId
            },
            body: {
                error: {
                    code: "INTERNAL_SERVER_ERROR",
                    message: "An unexpected server error occurred",
                    requestId
                }
            }
        };
    }
}


// ============================================================================
// 10. URL QUERY PARAMETER PARSING
// ============================================================================

function parseProductQuery(urlString) {
    const url = new URL(
        urlString,
        "https://example.test"
    );

    const parameters = url.searchParams;

    const parseOptionalNumber = name => {
        const value = parameters.get(name);

        if (value === null) {
            return undefined;
        }

        const number = Number(value);

        if (!Number.isFinite(number)) {
            throw new APIError(
                "INVALID_QUERY_PARAMETER",
                `${name} must be numeric`,
                400
            );
        }

        return number;
    };

    const activeValue = parameters.get("active");

    let active;

    if (activeValue !== null) {
        if (activeValue === "true") {
            active = true;
        } else if (activeValue === "false") {
            active = false;
        } else {
            throw new APIError(
                "INVALID_BOOLEAN",
                "active must be true or false",
                400
            );
        }
    }

    return {
        page: Number(parameters.get("page") ?? "1"),
        pageSize: Number(parameters.get("pageSize") ?? "10"),
        category: parameters.get("category") ?? undefined,
        minPrice: parseOptionalNumber("minPrice"),
        maxPrice: parseOptionalNumber("maxPrice"),
        minStock: parseOptionalNumber("minStock"),
        active,
        search: parameters.get("search") ?? undefined,
        sortBy: parameters.get("sortBy") ?? "id",
        descending: parameters.get("order") === "desc"
    };
}


// ============================================================================
// 11. CURSOR PAGINATION
// ============================================================================

function encodeCursor(id) {
    return Buffer
        .from(String(id), "utf8")
        .toString("base64url");
}

function decodeCursor(cursor) {
    try {
        const value = Buffer
            .from(cursor, "base64url")
            .toString("utf8");

        const id = Number(value);

        if (!Number.isInteger(id) || id < 0) {
            throw new Error("Invalid cursor");
        }

        return id;
    } catch {
        throw new APIError(
            "INVALID_CURSOR",
            "The supplied cursor is invalid",
            400
        );
    }
}

function getCursorPage(products, {
    limit = 10,
    cursor
} = {}) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
        throw new APIError(
            "INVALID_LIMIT",
            "limit must be between 1 and 100",
            400
        );
    }

    const ordered = [...products].sort(
        (a, b) => a.id - b.id
    );

    let startIndex = 0;

    if (cursor !== undefined) {
        const lastId = decodeCursor(cursor);

        const index = ordered.findIndex(
            product => product.id > lastId
        );

        startIndex = index === -1
            ? ordered.length
            : index;
    }

    const data = ordered.slice(
        startIndex,
        startIndex + limit
    );

    const hasMore =
        startIndex + limit < ordered.length;

    const nextCursor =
        data.length > 0 && hasMore
            ? encodeCursor(data[data.length - 1].id)
            : null;

    return {
        data,
        pagination: {
            limit,
            nextCursor,
            hasMore
        }
    };
}


// ============================================================================
// 12. RETRY WITH EXPONENTIAL BACKOFF
// ============================================================================

async function retryOperation(
    operation,
    {
        retries = 3,
        initialDelayMs = 50,
        shouldRetry = error => error?.status >= 500
    } = {}
) {
    let attempt = 0;

    while (true) {
        try {
            return await operation();
        } catch (error) {
            if (
                attempt >= retries ||
                !shouldRetry(error)
            ) {
                throw error;
            }

            const delay =
                initialDelayMs * (2 ** attempt);

            // Production systems commonly add jitter to prevent many clients
            // from retrying simultaneously.
            const jitter = Math.floor(
                Math.random() * Math.max(1, delay / 2)
            );

            await new Promise(resolve =>
                setTimeout(
                    resolve,
                    delay + jitter
                )
            );

            attempt += 1;
        }
    }
}


// ============================================================================
// 13. SAMPLE DATA
// ============================================================================

const products = [
    new Product({
        id: 1,
        name: "Laptop Pro",
        category: "electronics",
        price: 1499.99,
        stock: 12
    }),
    new Product({
        id: 2,
        name: "Wireless Mouse",
        category: "electronics",
        price: 29.99,
        stock: 80
    }),
    new Product({
        id: 3,
        name: "Mechanical Keyboard",
        category: "electronics",
        price: 119,
        stock: 35
    }),
    new Product({
        id: 4,
        name: "Office Chair",
        category: "furniture",
        price: 299.5,
        stock: 17
    }),
    new Product({
        id: 5,
        name: "Standing Desk",
        category: "furniture",
        price: 499,
        stock: 8
    }),
    new Product({
        id: 6,
        name: "Notebook",
        category: "stationery",
        price: 7.99,
        stock: 250
    }),
    new Product({
        id: 7,
        name: "Pen Set",
        category: "stationery",
        price: 12.5,
        stock: 120
    }),
    new Product({
        id: 8,
        name: "Monitor",
        category: "electronics",
        price: 349.99,
        stock: 20
    }),
    new Product({
        id: 9,
        name: "Desk Lamp",
        category: "furniture",
        price: 45,
        stock: 40
    }),
    new Product({
        id: 10,
        name: "USB Hub",
        category: "electronics",
        price: 39.99,
        stock: 55
    }),
    new Product({
        id: 11,
        name: "Webcam",
        category: "electronics",
        price: 89.99,
        stock: 28
    }),
    new Product({
        id: 12,
        name: "Bookshelf",
        category: "furniture",
        price: 180,
        stock: 4
    })
];


// ============================================================================
// 14. APPLICATION ASSEMBLY
// ============================================================================

const repository = new ProductRepository(products);
const service = new ProductService(repository);
const api = new ProductAPI(service);


// ============================================================================
// 15. DEMONSTRATIONS
// ============================================================================

async function main() {
    console.log("\n" + "=".repeat(78));
    console.log("2. VERSIONED GET REQUEST");
    console.log("=".repeat(78));

    const v1 = await api.getProduct(1, "v1");
    console.log(JSON.stringify(v1, null, 2));

    const v2 = await api.getProduct(1, "v2");
    console.log(JSON.stringify(v2, null, 2));


    console.log("\n" + "=".repeat(78));
    console.log("3. FILTERING, SORTING, AND PAGINATION");
    console.log("=".repeat(78));

    const filtered = await api.listProducts({
        version: "v2",
        page: 1,
        pageSize: 4,
        category: "electronics",
        minPrice: 50,
        maxPrice: 500,
        minStock: 10,
        sortBy: "price"
    });

    console.log(JSON.stringify(filtered, null, 2));


    console.log("\n" + "=".repeat(78));
    console.log("4. QUERY STRING PARSING");
    console.log("=".repeat(78));

    const query = parseProductQuery(
        "/api/v2/products?page=1&pageSize=3" +
        "&category=electronics&minPrice=50" +
        "&sortBy=price&order=desc"
    );

    console.log(query);


    console.log("\n" + "=".repeat(78));
    console.log("5. CURSOR PAGINATION");
    console.log("=".repeat(78));

    let cursor;

    for (let iteration = 1; iteration <= 4; iteration += 1) {
        const page = getCursorPage(products, {
            limit: 4,
            cursor
        });

        console.log(`Cursor page ${iteration}:`);
        console.log(
            page.data.map(product => product.id)
        );

        cursor = page.pagination.nextCursor;

        console.log(
            "Next cursor:",
            cursor
        );

        if (!page.pagination.hasMore) {
            break;
        }
    }


    console.log("\n" + "=".repeat(78));
    console.log("6. ERROR HANDLING");
    console.log("=".repeat(78));

    const errorResponses = [
        await api.getProduct(9999),
        await api.getProduct(1, "v99"),
        await api.listProducts({
            page: 0
        }),
        await api.listProducts({
            pageSize: 500
        }),
        await api.listProducts({
            sortBy: "password"
        })
    ];

    for (const response of errorResponses) {
        console.log(
            `HTTP ${response.status}`,
            JSON.stringify(response.body)
        );
    }


    console.log("\n" + "=".repeat(78));
    console.log("7. IDEMPOTENT CREATE");
    console.log("=".repeat(78));

    const newProduct = {
        id: 20,
        name: "API Design Handbook",
        category: "books",
        price: 49.99,
        stock: 10
    };

    const firstCreate = await api.createProduct(
        newProduct,
        {
            version: "v2",
            idempotencyKey: "create-001"
        }
    );

    const secondCreate = await api.createProduct(
        newProduct,
        {
            version: "v2",
            idempotencyKey: "create-001"
        }
    );

    console.log(
        "First create:",
        JSON.stringify(firstCreate, null, 2)
    );

    console.log(
        "Retry:",
        JSON.stringify(secondCreate, null, 2)
    );


    console.log("\n" + "=".repeat(78));
    console.log("8. ASYNCHRONOUS RETRY");
    console.log("=".repeat(78));

    let attempts = 0;

    const retryResult = await retryOperation(
        async () => {
            attempts += 1;

            if (attempts < 3) {
                throw new APIError(
                    "TEMPORARY_FAILURE",
                    "Simulated transient server failure",
                    503
                );
            }

            return {
                success: true,
                attempts
            };
        },
        {
            retries: 3,
            initialDelayMs: 10
        }
    );

    console.log(retryResult);


    console.log("\n" + "=".repeat(78));
    console.log("9. HTTP DESIGN RULES");
    console.log("=".repeat(78));

    const designRules = [
        "Use nouns for resource paths.",
        "Use HTTP methods according to their intended semantics.",
        "Use status codes to communicate outcome.",
        "Keep response shapes predictable.",
        "Use stable machine-readable error codes.",
        "Validate all client-controlled input.",
        "Allow-list fields used for sorting and filtering.",
        "Limit pagination size.",
        "Treat cursors as opaque.",
        "Version breaking contract changes.",
        "Make retryable operations safe through idempotency where appropriate.",
        "Never expose internal exception details to clients.",
        "Use authentication and authorization for protected resources.",
        "Use request IDs for operational troubleshooting."
    ];

    designRules.forEach(
        (rule, index) => console.log(`${index + 1}. ${rule}`)
    );
}


// ============================================================================
// 16. EXECUTABLE TESTS
// ============================================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

async function runTests() {
    console.log("\n" + "=".repeat(78));
    console.log("10. TESTS");
    console.log("=".repeat(78));

    const existing = await api.getProduct(1);
    assert(
        existing.status === 200,
        "existing product should return 200"
    );

    const missing = await api.getProduct(999999);
    assert(
        missing.status === 404,
        "missing product should return 404"
    );

    const paginated = await api.listProducts({
        page: 2,
        pageSize: 3
    });

    assert(
        paginated.status === 200,
        "pagination should succeed"
    );

    assert(
        paginated.body.data.length === 3,
        "second page should contain three items"
    );

    const filtered = await api.listProducts({
        category: "electronics",
        minPrice: 100
    });

    assert(
        filtered.status === 200,
        "filtering should succeed"
    );

    for (const product of filtered.body.data) {
        assert(
            product.category === "electronics",
            "category filter should be respected"
        );

        assert(
            product.price >= 100,
            "minimum price filter should be respected"
        );
    }

    const invalidCursor = (() => {
        try {
            getCursorPage(products, {
                limit: 3,
                cursor: "not-a-valid-cursor"
            });

            return false;
        } catch (error) {
            return error instanceof APIError &&
                error.code === "INVALID_CURSOR";
        }
    })();

    assert(
        invalidCursor,
        "invalid cursor should produce a structured API error"
    );

    const version1 = await api.getProduct(1, "v1");
    const version2 = await api.getProduct(1, "v2");

    assert(
        "price" in version1.body.data,
        "v1 should contain price"
    );

    assert(
        "pricing" in version2.body.data,
        "v2 should contain structured pricing"
    );

    console.log("PASS: existing product");
    console.log("PASS: missing product");
    console.log("PASS: pagination");
    console.log("PASS: filtering");
    console.log("PASS: cursor validation");
    console.log("PASS: versioning");
}


// ============================================================================
// 17. START PROGRAM
// ============================================================================

(async () => {
    try {
        await main();
        await runTests();

        console.log("\nAll JavaScript API demonstrations completed.");
    } catch (error) {
        console.error("Unexpected application failure:", error);
        process.exitCode = 1;
    }
})();
