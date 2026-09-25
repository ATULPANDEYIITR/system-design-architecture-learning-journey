/*
 * API Design Case Study
 * =====================
 *
 * Scenario:
 *     A production-oriented Product Catalog API.
 *
 * Topics:
 *     - API versioning
 *     - filtering
 *     - sorting
 *     - offset pagination
 *     - cursor pagination
 *     - validation
 *     - structured errors
 *     - idempotency
 *     - HTTP semantics
 *     - service/repository architecture
 *     - performance and complexity
 *     - security-oriented validation
 *
 * Compile:
 *     g++ -std=c++17 -O2 -Wall -Wextra -pedantic api_design.cpp -o api_design
 *
 * Run:
 *     ./api_design
 *
 * The program uses only the C++ standard library.
 */

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;


// ============================================================================
// 1. HTTP-STYLE RESPONSE MODEL
// ============================================================================

struct APIError {
    string code;
    string message;
    int status;
    map<string, string> details;
};

struct APIResponse {
    int status;
    map<string, string> headers;
    string body;
};


// ============================================================================
// 2. DOMAIN MODEL
// ============================================================================

struct Product {
    int id;
    string name;
    string category;
    double price;
    int stock;
    bool active;
    string createdAt;
};


// ============================================================================
// 3. VALIDATION HELPERS
// ============================================================================

bool isFinite(double value) {
    return std::isfinite(value);
}

void validateProduct(const Product& product) {
    if (product.id <= 0) {
        throw APIError{
            "INVALID_PRODUCT_ID",
            "Product ID must be positive.",
            422,
            {}
        };
    }

    if (product.name.empty()) {
        throw APIError{
            "INVALID_NAME",
            "Product name cannot be empty.",
            422,
            {}
        };
    }

    if (product.category.empty()) {
        throw APIError{
            "INVALID_CATEGORY",
            "Product category cannot be empty.",
            422,
            {}
        };
    }

    if (!isFinite(product.price) || product.price < 0) {
        throw APIError{
            "INVALID_PRICE",
            "Price must be a finite non-negative number.",
            422,
            {}
        };
    }

    if (product.stock < 0) {
        throw APIError{
            "INVALID_STOCK",
            "Stock cannot be negative.",
            422,
            {}
        };
    }
}


// ============================================================================
// 4. JSON-LIKE OUTPUT HELPERS
// ============================================================================

string escapeString(const string& input) {
    string output;

    for (char character : input) {
        switch (character) {
            case '\\':
                output += "\\\\";
                break;
            case '"':
                output += "\\\"";
                break;
            case '\n':
                output += "\\n";
                break;
            case '\r':
                output += "\\r";
                break;
            case '\t':
                output += "\\t";
                break;
            default:
                output += character;
        }
    }

    return output;
}

string boolJson(bool value) {
    return value ? "true" : "false";
}

string productJsonV1(const Product& product) {
    ostringstream output;

    output << "{"
           << "\"id\":" << product.id << ","
           << "\"name\":\"" << escapeString(product.name) << "\","
           << "\"category\":\"" << escapeString(product.category) << "\","
           << "\"price\":" << fixed << setprecision(2)
           << product.price << ","
           << "\"stock\":" << product.stock << ","
           << "\"active\":" << boolJson(product.active)
           << "}";

    return output.str();
}

string productJsonV2(const Product& product) {
    ostringstream output;

    output << "{"
           << "\"id\":" << product.id << ","
           << "\"name\":\"" << escapeString(product.name) << "\","
           << "\"category\":\"" << escapeString(product.category) << "\","
           << "\"pricing\":{"
           << "\"amount\":" << fixed << setprecision(2)
           << product.price << ","
           << "\"currency\":\"USD\""
           << "},"
           << "\"inventory\":{"
           << "\"stock\":" << product.stock << ","
           << "\"available\":"
           << boolJson(product.stock > 0)
           << "},"
           << "\"active\":" << boolJson(product.active) << ","
           << "\"createdAt\":\""
           << escapeString(product.createdAt)
           << "\""
           << "}";

    return output.str();
}


// ============================================================================
// 5. ERROR SERIALIZATION
// ============================================================================

string errorJson(
    const APIError& error,
    const string& requestId
) {
    ostringstream output;

    output << "{"
           << "\"error\":{"
           << "\"code\":\"" << escapeString(error.code) << "\","
           << "\"message\":\"" << escapeString(error.message) << "\","
           << "\"requestId\":\"" << escapeString(requestId) << "\"";

    if (!error.details.empty()) {
        output << ",\"details\":{";

        bool first = true;

        for (const auto& [key, value] : error.details) {
            if (!first) {
                output << ",";
            }

            output << "\""
                   << escapeString(key)
                   << "\":\""
                   << escapeString(value)
                   << "\"";

            first = false;
        }

        output << "}";
    }

    output << "}}";

    return output.str();
}


// ============================================================================
// 6. VERSION POLICY
// ============================================================================

enum class APIVersion {
    V1,
    V2
};

optional<APIVersion> parseVersion(const string& version) {
    if (version == "v1") {
        return APIVersion::V1;
    }

    if (version == "v2") {
        return APIVersion::V2;
    }

    return nullopt;
}

string serializeProduct(
    const Product& product,
    APIVersion version
) {
    if (version == APIVersion::V1) {
        return productJsonV1(product);
    }

    return productJsonV2(product);
}


// ============================================================================
// 7. REPOSITORY
// ============================================================================

class ProductRepository {
private:
    unordered_map<int, Product> products;

public:
    void add(const Product& product) {
        validateProduct(product);

        if (products.find(product.id) != products.end()) {
            throw APIError{
                "PRODUCT_ALREADY_EXISTS",
                "A product with this ID already exists.",
                409,
                {{"id", to_string(product.id)}}
            };
        }

        products.emplace(product.id, product);
    }

    optional<Product> get(int id) const {
        auto iterator = products.find(id);

        if (iterator == products.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    vector<Product> list() const {
        vector<Product> result;

        result.reserve(products.size());

        for (const auto& [id, product] : products) {
            result.push_back(product);
        }

        return result;
    }
};


// ============================================================================
// 8. FILTER SPECIFICATION
// ============================================================================

struct ProductFilter {
    optional<string> category;
    optional<double> minPrice;
    optional<double> maxPrice;
    optional<int> minStock;
    optional<bool> active;
    optional<string> search;
};

void validateFilter(const ProductFilter& filter) {
    if (filter.minPrice.has_value()) {
        if (!isFinite(*filter.minPrice) || *filter.minPrice < 0) {
            throw APIError{
                "INVALID_MIN_PRICE",
                "minPrice must be non-negative.",
                400,
                {}
            };
        }
    }

    if (filter.maxPrice.has_value()) {
        if (!isFinite(*filter.maxPrice) || *filter.maxPrice < 0) {
            throw APIError{
                "INVALID_MAX_PRICE",
                "maxPrice must be non-negative.",
                400,
                {}
            };
        }
    }

    if (
        filter.minPrice.has_value() &&
        filter.maxPrice.has_value() &&
        *filter.minPrice > *filter.maxPrice
    ) {
        throw APIError{
            "INVALID_PRICE_RANGE",
            "minPrice cannot exceed maxPrice.",
            400,
            {}
        };
    }

    if (filter.minStock.has_value() && *filter.minStock < 0) {
        throw APIError{
            "INVALID_MIN_STOCK",
            "minStock cannot be negative.",
            400,
            {}
        };
    }
}


// ============================================================================
// 9. FILTERING ALGORITHM
// ============================================================================

vector<Product> applyFilters(
    vector<Product> products,
    const ProductFilter& filter
) {
    validateFilter(filter);

    vector<Product> result;

    for (const Product& product : products) {
        bool matches = true;

        if (
            filter.category.has_value() &&
            product.category != *filter.category
        ) {
            matches = false;
        }

        if (
            filter.minPrice.has_value() &&
            product.price < *filter.minPrice
        ) {
            matches = false;
        }

        if (
            filter.maxPrice.has_value() &&
            product.price > *filter.maxPrice
        ) {
            matches = false;
        }

        if (
            filter.minStock.has_value() &&
            product.stock < *filter.minStock
        ) {
            matches = false;
        }

        if (
            filter.active.has_value() &&
            product.active != *filter.active
        ) {
            matches = false;
        }

        if (filter.search.has_value()) {
            const string& term = *filter.search;

            if (
                product.name.find(term) == string::npos &&
                product.category.find(term) == string::npos
            ) {
                matches = false;
            }
        }

        if (matches) {
            result.push_back(product);
        }
    }

    return result;
}


// ============================================================================
// 10. SORTING
// ============================================================================

enum class SortField {
    ID,
    NAME,
    CATEGORY,
    PRICE,
    STOCK
};

optional<SortField> parseSortField(const string& field) {
    if (field == "id") {
        return SortField::ID;
    }

    if (field == "name") {
        return SortField::NAME;
    }

    if (field == "category") {
        return SortField::CATEGORY;
    }

    if (field == "price") {
        return SortField::PRICE;
    }

    if (field == "stock") {
        return SortField::STOCK;
    }

    return nullopt;
}

void sortProducts(
    vector<Product>& products,
    SortField field,
    bool descending
) {
    auto comparator = [field, descending](
        const Product& left,
        const Product& right
    ) {
        bool less;

        switch (field) {
            case SortField::ID:
                less = left.id < right.id;
                break;

            case SortField::NAME:
                less = left.name < right.name;
                break;

            case SortField::CATEGORY:
                less = left.category < right.category;
                break;

            case SortField::PRICE:
                less = left.price < right.price;
                break;

            case SortField::STOCK:
                less = left.stock < right.stock;
                break;
        }

        if (less) {
            return !descending;
        }

        if (
            left.id != right.id &&
            left.name == right.name &&
            left.category == right.category &&
            left.price == right.price &&
            left.stock == right.stock
        ) {
            return left.id < right.id;
        }

        return descending;
    };

    sort(
        products.begin(),
        products.end(),
        comparator
    );
}


// ============================================================================
// 11. PAGINATION
// ============================================================================

struct PaginationResult {
    vector<Product> data;
    int page;
    int pageSize;
    size_t totalItems;
    size_t totalPages;
    bool hasPrevious;
    bool hasNext;
};

PaginationResult paginate(
    const vector<Product>& products,
    int page,
    int pageSize
) {
    if (page < 1) {
        throw APIError{
            "INVALID_PAGE",
            "page must be at least 1.",
            400,
            {}
        };
    }

    if (pageSize < 1 || pageSize > 100) {
        throw APIError{
            "INVALID_PAGE_SIZE",
            "pageSize must be between 1 and 100.",
            400,
            {}
        };
    }

    const size_t totalItems = products.size();

    const size_t totalPages =
        totalItems == 0
            ? 0
            : (totalItems + pageSize - 1) / pageSize;

    const size_t offset =
        static_cast<size_t>(page - 1) *
        static_cast<size_t>(pageSize);

    vector<Product> data;

    if (offset < totalItems) {
        const size_t end =
            min(
                offset + static_cast<size_t>(pageSize),
                totalItems
            );

        data.insert(
            data.end(),
            products.begin() + static_cast<long>(offset),
            products.begin() + static_cast<long>(end)
        );
    }

    return {
        data,
        page,
        pageSize,
        totalItems,
        totalPages,
        page > 1 && totalPages > 0,
        page < static_cast<int>(totalPages)
    };
}


// ============================================================================
// 12. CURSOR PAGINATION
// ============================================================================

struct CursorPage {
    vector<Product> data;
    optional<int> nextCursor;
    bool hasMore;
};

CursorPage cursorPaginate(
    vector<Product> products,
    int limit,
    optional<int> cursor
) {
    if (limit < 1 || limit > 100) {
        throw APIError{
            "INVALID_LIMIT",
            "limit must be between 1 and 100.",
            400,
            {}
        };
    }

    sort(
        products.begin(),
        products.end(),
        [](const Product& left, const Product& right) {
            return left.id < right.id;
        }
    );

    size_t start = 0;

    if (cursor.has_value()) {
        while (
            start < products.size() &&
            products[start].id <= *cursor
        ) {
            ++start;
        }
    }

    vector<Product> selected;

    const size_t end =
        min(
            start + static_cast<size_t>(limit),
            products.size()
        );

    for (size_t index = start; index < end; ++index) {
        selected.push_back(products[index]);
    }

    const bool hasMore = end < products.size();

    optional<int> nextCursor;

    if (hasMore && !selected.empty()) {
        nextCursor = selected.back().id;
    }

    return {
        selected,
        nextCursor,
        hasMore
    };
}


// ============================================================================
// 13. SERVICE LAYER
// ============================================================================

class ProductService {
private:
    const ProductRepository& repository;

public:
    explicit ProductService(
        const ProductRepository& repository
    )
        : repository(repository) {}

    Product getProduct(int id) const {
        if (id <= 0) {
            throw APIError{
                "INVALID_PRODUCT_ID",
                "Product ID must be positive.",
                400,
                {}
            };
        }

        const auto product = repository.get(id);

        if (!product.has_value()) {
            throw APIError{
                "PRODUCT_NOT_FOUND",
                "The requested product does not exist.",
                404,
                {{"id", to_string(id)}}
            };
        }

        return *product;
    }

    PaginationResult listProducts(
        const ProductFilter& filter,
        int page,
        int pageSize,
        const string& sortField,
        bool descending
    ) const {
        auto products = applyFilters(
            repository.list(),
            filter
        );

        const auto parsedSort = parseSortField(sortField);

        if (!parsedSort.has_value()) {
            throw APIError{
                "INVALID_SORT_FIELD",
                "Unsupported sort field.",
                400,
                {{"field", sortField}}
            };
        }

        sortProducts(
            products,
            *parsedSort,
            descending
        );

        return paginate(
            products,
            page,
            pageSize
        );
    }
};


// ============================================================================
// 14. IDEMPOTENCY STORE
// ============================================================================

class IdempotencyStore {
private:
    unordered_map<string, APIResponse> responses;

public:
    optional<APIResponse> find(
        const string& key
    ) const {
        auto iterator = responses.find(key);

        if (iterator == responses.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    void save(
        const string& key,
        const APIResponse& response
    ) {
        responses[key] = response;
    }
};


// ============================================================================
// 15. API CONTROLLER
// ============================================================================

class ProductAPI {
private:
    const ProductService& service;
    IdempotencyStore idempotencyStore;

    static string requestId() {
        static uint64_t counter = 0;
        ++counter;

        return "req-" + to_string(counter);
    }

    static APIResponse errorResponse(
        const APIError& error,
        const string& requestIdValue
    ) {
        return {
            error.status,
            {
                {"Content-Type", "application/json"},
                {"X-Request-ID", requestIdValue}
            },
            errorJson(error, requestIdValue)
        };
    }

public:
    explicit ProductAPI(
        const ProductService& service
    )
        : service(service) {}

    APIResponse getProduct(
        int id,
        const string& version
    ) const {
        const string idValue = requestId();

        try {
            const auto parsedVersion =
                parseVersion(version);

            if (!parsedVersion.has_value()) {
                throw APIError{
                    "UNSUPPORTED_API_VERSION",
                    "Unsupported API version.",
                    400,
                    {{"version", version}}
                };
            }

            const Product product =
                service.getProduct(id);

            return {
                200,
                {
                    {"Content-Type", "application/json"},
                    {"X-Request-ID", idValue},
                    {"API-Version", version}
                },
                string("{\"data\":") +
                    serializeProduct(
                        product,
                        *parsedVersion
                    ) +
                    "}"
            };
        }
        catch (const APIError& error) {
            return errorResponse(
                error,
                idValue
            );
        }
    }

    APIResponse createProduct(
        const Product& product,
        const string& version,
        const optional<string>& idempotencyKey
    ) {
        const string idValue = requestId();

        try {
            const auto parsedVersion =
                parseVersion(version);

            if (!parsedVersion.has_value()) {
                throw APIError{
                    "UNSUPPORTED_API_VERSION",
                    "Unsupported API version.",
                    400,
                    {{"version", version}}
                };
            }

            if (idempotencyKey.has_value()) {
                const auto previous =
                    idempotencyStore.find(
                        *idempotencyKey
                    );

                if (previous.has_value()) {
                    return *previous;
                }
            }

            validateProduct(product);

            /*
             * In a real service this operation would call the repository.
             * This case study keeps creation focused on the API contract
             * and idempotency mechanism.
             */
            const APIResponse response = {
                201,
                {
                    {"Content-Type", "application/json"},
                    {"X-Request-ID", idValue},
                    {"API-Version", version},
                    {
                        "Location",
                        "/api/" + version +
                        "/products/" +
                        to_string(product.id)
                    }
                },
                string("{\"data\":") +
                    serializeProduct(
                        product,
                        *parsedVersion
                    ) +
                    "}"
            };

            if (idempotencyKey.has_value()) {
                idempotencyStore.save(
                    *idempotencyKey,
                    response
                );
            }

            return response;
        }
        catch (const APIError& error) {
            return errorResponse(
                error,
                idValue
            );
        }
    }
};


// ============================================================================
// 16. OUTPUT FUNCTIONS
// ============================================================================

void printResponse(
    const APIResponse& response
) {
    cout << "HTTP " << response.status << "\n";

    for (const auto& [name, value] : response.headers) {
        cout << name << ": " << value << "\n";
    }

    cout << response.body << "\n";
}

void printProductIDs(
    const vector<Product>& products
) {
    cout << "[";

    for (size_t index = 0; index < products.size(); ++index) {
        if (index > 0) {
            cout << ", ";
        }

        cout << products[index].id;
    }

    cout << "]\n";
}


// ============================================================================
// 17. TESTING
// ============================================================================

void require(
    bool condition,
    const string& message
) {
    if (!condition) {
        throw runtime_error(
            "Test failed: " + message
        );
    }
}

void runTests(
    const ProductAPI& api,
    const ProductService& service,
    const ProductRepository& repository
) {
    const auto existing =
        api.getProduct(1, "v1");

    require(
        existing.status == 200,
        "existing product should return 200"
    );

    const auto missing =
        api.getProduct(9999, "v1");

    require(
        missing.status == 404,
        "missing product should return 404"
    );

    ProductFilter electronics;
    electronics.category = "electronics";
    electronics.minPrice = 50.0;

    const auto page =
        service.listProducts(
            electronics,
            1,
            3,
            "price",
            false
        );

    require(
        page.data.size() <= 3,
        "page must respect page size"
    );

    for (const auto& product : page.data) {
        require(
            product.category == "electronics",
            "category filter must be respected"
        );

        require(
            product.price >= 50.0,
            "price filter must be respected"
        );
    }

    const auto cursorFirst =
        cursorPaginate(
            repository.list(),
            3,
            nullopt
        );

    require(
        cursorFirst.data.size() == 3,
        "cursor first page should contain three products"
    );

    require(
        cursorFirst.hasMore,
        "first cursor page should have another page"
    );

    const auto cursorSecond =
        cursorPaginate(
            repository.list(),
            3,
            cursorFirst.nextCursor
        );

    require(
        !cursorSecond.data.empty(),
        "second cursor page should contain products"
    );

    require(
        cursorSecond.data.front().id >
            cursorFirst.data.back().id,
        "cursor pagination must advance"
    );

    cout << "All tests passed.\n";
}


// ============================================================================
// 18. MAIN CASE STUDY
// ============================================================================

int main() {
    try {
        cout << string(78, '=') << "\n";
        cout << "API DESIGN CASE STUDY\n";
        cout << string(78, '=') << "\n";

        ProductRepository repository;

        repository.add({
            1,
            "Laptop Pro",
            "electronics",
            1499.99,
            12,
            true,
            "2026-09-01T10:00:00Z"
        });

        repository.add({
            2,
            "Wireless Mouse",
            "electronics",
            29.99,
            80,
            true,
            "2026-09-02T10:00:00Z"
        });

        repository.add({
            3,
            "Mechanical Keyboard",
            "electronics",
            119.00,
            35,
            true,
            "2026-09-03T10:00:00Z"
        });

        repository.add({
            4,
            "Office Chair",
            "furniture",
            299.50,
            17,
            true,
            "2026-09-04T10:00:00Z"
        });

        repository.add({
            5,
            "Standing Desk",
            "furniture",
            499.00,
            8,
            true,
            "2026-09-05T10:00:00Z"
        });

        repository.add({
            6,
            "Notebook",
            "stationery",
            7.99,
            250,
            true,
            "2026-09-06T10:00:00Z"
        });

        repository.add({
            7,
            "Pen Set",
            "stationery",
            12.50,
            120,
            true,
            "2026-09-07T10:00:00Z"
        });

        repository.add({
            8,
            "Monitor",
            "electronics",
            349.99,
            20,
            true,
            "2026-09-08T10:00:00Z"
        });

        repository.add({
            9,
            "Desk Lamp",
            "furniture",
            45.00,
            40,
            true,
            "2026-09-09T10:00:00Z"
        });

        repository.add({
            10,
            "USB Hub",
            "electronics",
            39.99,
            55,
            true,
            "2026-09-10T10:00:00Z"
        });

        ProductService service(repository);
        ProductAPI api(service);


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "1. API VERSIONING: V1\n";
        cout << string(78, '-') << "\n";

        printResponse(
            api.getProduct(1, "v1")
        );


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "2. API VERSIONING: V2\n";
        cout << string(78, '-') << "\n";

        printResponse(
            api.getProduct(1, "v2")
        );


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "3. FILTERING AND SORTING\n";
        cout << string(78, '-') << "\n";

        ProductFilter filter;
        filter.category = "electronics";
        filter.minPrice = 50.0;
        filter.maxPrice = 500.0;
        filter.minStock = 10;

        const auto filtered =
            service.listProducts(
                filter,
                1,
                4,
                "price",
                false
            );

        cout << "Filtered product IDs: ";
        printProductIDs(filtered.data);

        cout << "Total matching items: "
             << filtered.totalItems
             << "\n";

        cout << "Total pages: "
             << filtered.totalPages
             << "\n";


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "4. OFFSET PAGINATION\n";
        cout << string(78, '-') << "\n";

        ProductFilter noFilter;

        for (int page = 1; page <= 3; ++page) {
            const auto result =
                service.listProducts(
                    noFilter,
                    page,
                    3,
                    "id",
                    false
                );

            cout << "Page "
                 << page
                 << ": ";

            printProductIDs(result.data);
        }


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "5. CURSOR PAGINATION\n";
        cout << string(78, '-') << "\n";

        optional<int> cursor;

        for (int iteration = 1; iteration <= 4; ++iteration) {
            const auto result =
                cursorPaginate(
                    repository.list(),
                    3,
                    cursor
                );

            cout << "Cursor page "
                 << iteration
                 << ": ";

            printProductIDs(result.data);

            if (result.nextCursor.has_value()) {
                cout << "Next cursor: "
                     << *result.nextCursor
                     << "\n";

                cursor = result.nextCursor;
            } else {
                cout << "No next cursor.\n";
                break;
            }
        }


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "6. ERROR HANDLING\n";
        cout << string(78, '-') << "\n";

        printResponse(
            api.getProduct(
                9999,
                "v1"
            )
        );

        printResponse(
            api.getProduct(
                1,
                "v99"
            )
        );


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "7. IDEMPOTENT CREATE\n";
        cout << string(78, '-') << "\n";

        Product newProduct{
            50,
            "API Design Handbook",
            "books",
            49.99,
            10,
            true,
            "2026-09-25T10:00:00Z"
        };

        const string idempotencyKey =
            "client-request-50";

        const auto firstCreate =
            api.createProduct(
                newProduct,
                "v2",
                idempotencyKey
            );

        const auto retryCreate =
            api.createProduct(
                newProduct,
                "v2",
                idempotencyKey
            );

        cout << "First request:\n";
        printResponse(firstCreate);

        cout << "\nRetry with the same idempotency key:\n";
        printResponse(retryCreate);


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "8. EDGE CASES\n";
        cout << string(78, '-') << "\n";

        try {
            ProductFilter invalidFilter;
            invalidFilter.minPrice = 500.0;
            invalidFilter.maxPrice = 100.0;

            service.listProducts(
                invalidFilter,
                1,
                10,
                "id",
                false
            );
        }
        catch (const APIError& error) {
            cout << "Caught expected error: "
                 << error.code
                 << " / "
                 << error.message
                 << "\n";
        }

        try {
            service.listProducts(
                noFilter,
                1,
                1000,
                "id",
                false
            );
        }
        catch (const APIError& error) {
            cout << "Caught expected pagination error: "
                 << error.code
                 << " / "
                 << error.message
                 << "\n";
        }


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "9. COMPLEXITY AND DESIGN NOTES\n";
        cout << string(78, '-') << "\n";

        cout
            << "Repository lookup: average O(1) with unordered_map.\n"
            << "In-memory filtering: O(n).\n"
            << "Sorting: O(n log n).\n"
            << "Offset pagination after sorting: O(n log n) here because\n"
            << "the demonstration sorts before slicing.\n"
            << "Cursor pagination: O(n log n) in this in-memory demonstration,\n"
            << "but an indexed database cursor can approach O(log n + k),\n"
            << "where k is the number of returned rows.\n"
            << "Production systems should push filtering, sorting, and\n"
            << "pagination into the database whenever practical.\n";


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "10. SECURITY DESIGN\n";
        cout << string(78, '-') << "\n";

        const vector<string> securityRules = {
            "Validate every client-controlled value.",
            "Allow-list sortable and filterable fields.",
            "Limit page sizes.",
            "Use authentication for protected endpoints.",
            "Use authorization for every protected resource.",
            "Never return secrets or internal stack traces.",
            "Use HTTPS for network transport.",
            "Use parameterized queries in database implementations.",
            "Apply rate limits to resource-intensive endpoints.",
            "Log request IDs without logging sensitive credentials."
        };

        for (size_t index = 0;
             index < securityRules.size();
             ++index) {
            cout << index + 1
                 << ". "
                 << securityRules[index]
                 << "\n";
        }


        cout << "\n";
        cout << string(78, '-') << "\n";
        cout << "11. EXECUTABLE TESTS\n";
        cout << string(78, '-') << "\n";

        runTests(
            api,
            service,
            repository
        );


        cout << "\n";
        cout << string(78, '=') << "\n";
        cout << "CASE STUDY COMPLETED\n";
        cout << string(78, '=') << "\n";

        return 0;
    }
    catch (const APIError& error) {
        cerr << "API error: "
             << error.code
             << " - "
             << error.message
             << "\n";

        return 1;
    }
    catch (const exception& error) {
        cerr << "Unexpected error: "
             << error.what()
             << "\n";

        return 1;
    }
}
