/*
 * Web Architecture and REST APIs
 * Industry-style case study: Product Catalog REST Service
 *
 * C++17
 *
 * The program models a resource-oriented HTTP API without requiring an
 * external HTTP framework. It demonstrates the architectural concepts
 * behind REST while keeping storage and transport self-contained.
 */

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;

// =============================================================================
// Utility functions
// =============================================================================

string jsonEscape(const string& input) {
    string output;

    for (char character : input) {
        switch (character) {
            case '"':
                output += "\\\"";
                break;
            case '\\':
                output += "\\\\";
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

string trim(const string& value) {
    const auto first = value.find_first_not_of(" \t\n\r");

    if (first == string::npos) {
        return "";
    }

    const auto last = value.find_last_not_of(" \t\n\r");
    return value.substr(first, last - first + 1);
}

void section(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

// =============================================================================
// HTTP method model
// =============================================================================

enum class HttpMethod {
    GET,
    POST,
    PUT,
    PATCH,
    DELETE_METHOD,
    HEAD,
    OPTIONS
};

string methodToString(HttpMethod method) {
    switch (method) {
        case HttpMethod::GET:
            return "GET";
        case HttpMethod::POST:
            return "POST";
        case HttpMethod::PUT:
            return "PUT";
        case HttpMethod::PATCH:
            return "PATCH";
        case HttpMethod::DELETE_METHOD:
            return "DELETE";
        case HttpMethod::HEAD:
            return "HEAD";
        case HttpMethod::OPTIONS:
            return "OPTIONS";
    }

    return "UNKNOWN";
}

// =============================================================================
// Resource
// =============================================================================

struct Product {
    int id{};
    string name;
    string category;
    double price{};
    int stock{};
    bool active{true};
    string createdAt;

    string toJson() const {
        ostringstream output;

        output << fixed << setprecision(2);

        output << "{"
               << "\"id\":" << id << ","
               << "\"name\":\"" << jsonEscape(name) << "\","
               << "\"category\":\"" << jsonEscape(category) << "\","
               << "\"price\":" << price << ","
               << "\"stock\":" << stock << ","
               << "\"active\":" << (active ? "true" : "false") << ","
               << "\"created_at\":\"" << jsonEscape(createdAt) << "\""
               << "}";

        return output.str();
    }
};

// =============================================================================
// HTTP request and response
// =============================================================================

struct HttpRequest {
    HttpMethod method;
    string path;
    map<string, string> headers;
    map<string, string> query;
    map<string, string> body;
};

struct HttpResponse {
    int statusCode{};
    map<string, string> headers;
    string body;

    void print() const {
        cout << "HTTP Status: " << statusCode << "\n";

        if (!headers.empty()) {
            cout << "Headers:\n";

            for (const auto& [name, value] : headers) {
                cout << "  " << name << ": " << value << "\n";
            }
        }

        if (!body.empty()) {
            cout << "Body:\n";
            cout << body << "\n";
        }
    }
};

// =============================================================================
// Validation
// =============================================================================

class ValidationException : public runtime_error {
public:
    explicit ValidationException(const string& message)
        : runtime_error(message) {}
};

double parseNonNegativeDouble(const map<string, string>& body,
                              const string& field) {
    const auto iterator = body.find(field);

    if (iterator == body.end()) {
        throw ValidationException(field + " is required");
    }

    try {
        size_t processed = 0;
        const double value = stod(iterator->second, &processed);

        if (processed != iterator->second.size()) {
            throw ValidationException(field + " must be numeric");
        }

        if (!isfinite(value) || value < 0) {
            throw ValidationException(
                field + " must be finite and non-negative"
            );
        }

        return value;
    } catch (const invalid_argument&) {
        throw ValidationException(field + " must be numeric");
    } catch (const out_of_range&) {
        throw ValidationException(field + " is out of range");
    }
}

int parseNonNegativeInt(const map<string, string>& body,
                        const string& field) {
    const auto iterator = body.find(field);

    if (iterator == body.end()) {
        throw ValidationException(field + " is required");
    }

    try {
        size_t processed = 0;
        const long value = stol(iterator->second, &processed);

        if (processed != iterator->second.size()) {
            throw ValidationException(field + " must be an integer");
        }

        if (value < 0 || value > numeric_limits<int>::max()) {
            throw ValidationException(
                field + " must be a valid non-negative integer"
            );
        }

        return static_cast<int>(value);
    } catch (const invalid_argument&) {
        throw ValidationException(field + " must be an integer");
    } catch (const out_of_range&) {
        throw ValidationException(field + " is out of range");
    }
}

// =============================================================================
// Repository
// =============================================================================

class ProductRepository {
private:
    map<int, Product> products;
    int nextId{1};

    static string currentTimestamp() {
        using namespace chrono;

        const auto now = system_clock::now();
        const time_t timeValue = system_clock::to_time_t(now);

        tm utcTime{};

#if defined(_WIN32)
        gmtime_s(&utcTime, &timeValue);
#else
        gmtime_r(&timeValue, &utcTime);
#endif

        ostringstream output;
        output << put_time(&utcTime, "%Y-%m-%dT%H:%M:%SZ");

        return output.str();
    }

public:
    Product create(const string& name,
                   const string& category,
                   double price,
                   int stock) {
        Product product{
            nextId,
            name,
            category,
            price,
            stock,
            true,
            currentTimestamp()
        };

        products[nextId] = product;
        ++nextId;

        return product;
    }

    optional<Product> get(int id) const {
        const auto iterator = products.find(id);

        if (iterator == products.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    vector<Product> list() const {
        vector<Product> result;

        for (const auto& [id, product] : products) {
            result.push_back(product);
        }

        return result;
    }

    bool erase(int id) {
        return products.erase(id) > 0;
    }

    bool patch(int id,
               const optional<string>& name,
               const optional<string>& category,
               const optional<double>& price,
               const optional<int>& stock,
               const optional<bool>& active) {
        auto iterator = products.find(id);

        if (iterator == products.end()) {
            return false;
        }

        if (name.has_value()) {
            iterator->second.name = *name;
        }

        if (category.has_value()) {
            iterator->second.category = *category;
        }

        if (price.has_value()) {
            iterator->second.price = *price;
        }

        if (stock.has_value()) {
            iterator->second.stock = *stock;
        }

        if (active.has_value()) {
            iterator->second.active = *active;
        }

        return true;
    }
};

// =============================================================================
// Product API
// =============================================================================

class ProductApi {
private:
    ProductRepository repository;

    static bool matchesCategory(const Product& product,
                                 const string& category) {
        string left = product.category;
        string right = category;

        transform(
            left.begin(),
            left.end(),
            left.begin(),
            [](unsigned char character) {
                return static_cast<char>(tolower(character));
            }
        );

        transform(
            right.begin(),
            right.end(),
            right.begin(),
            [](unsigned char character) {
                return static_cast<char>(tolower(character));
            }
        );

        return left == right;
    }

    static HttpResponse errorResponse(
        int status,
        const string& code,
        const string& message) {
        HttpResponse response;
        response.statusCode = status;
        response.headers["Content-Type"] = "application/json";

        response.body =
            "{"
            "\"error\":{"
            "\"code\":\"" + jsonEscape(code) + "\","
            "\"message\":\"" + jsonEscape(message) + "\""
            "}"
            "}";

        return response;
    }

public:
    HttpResponse createProduct(const HttpRequest& request) {
        try {
            const auto nameIterator = request.body.find("name");

            if (nameIterator == request.body.end()) {
                throw ValidationException("name is required");
            }

            const string name = trim(nameIterator->second);

            if (name.empty()) {
                throw ValidationException(
                    "name must not be empty"
                );
            }

            const auto categoryIterator =
                request.body.find("category");

            const string category =
                categoryIterator == request.body.end()
                    ? "uncategorized"
                    : trim(categoryIterator->second);

            const double price =
                parseNonNegativeDouble(request.body, "price");

            const int stock =
                parseNonNegativeInt(request.body, "stock");

            Product product =
                repository.create(
                    name,
                    category,
                    price,
                    stock
                );

            HttpResponse response;
            response.statusCode = 201;
            response.headers["Content-Type"] =
                "application/json";
            response.headers["Location"] =
                "/api/v1/products/" + to_string(product.id);
            response.body =
                "{\"data\":" + product.toJson() + "}";

            return response;
        } catch (const ValidationException& exception) {
            return errorResponse(
                422,
                "VALIDATION_ERROR",
                exception.what()
            );
        }
    }

    HttpResponse getProduct(int id) const {
        const auto product = repository.get(id);

        if (!product.has_value()) {
            return errorResponse(
                404,
                "PRODUCT_NOT_FOUND",
                "Product " + to_string(id) + " was not found"
            );
        }

        HttpResponse response;
        response.statusCode = 200;
        response.headers["Content-Type"] =
            "application/json";
        response.body =
            "{\"data\":" + product->toJson() + "}";

        return response;
    }

    HttpResponse listProducts(
        const optional<string>& category = nullopt,
        const optional<double>& minimumPrice = nullopt,
        const optional<double>& maximumPrice = nullopt,
        int page = 1,
        int limit = 10) const {
        if (page < 1 || limit < 1 || limit > 100) {
            return errorResponse(
                400,
                "INVALID_PAGINATION",
                "page must be >= 1 and limit must be between 1 and 100"
            );
        }

        vector<Product> products =
            repository.list();

        vector<Product> filtered;

        for (const Product& product : products) {
            if (category.has_value() &&
                !matchesCategory(product, *category)) {
                continue;
            }

            if (minimumPrice.has_value() &&
                product.price < *minimumPrice) {
                continue;
            }

            if (maximumPrice.has_value() &&
                product.price > *maximumPrice) {
                continue;
            }

            filtered.push_back(product);
        }

        const size_t start =
            static_cast<size_t>(page - 1) *
            static_cast<size_t>(limit);

        const size_t end =
            min(
                start + static_cast<size_t>(limit),
                filtered.size()
            );

        ostringstream body;

        body << "{\"data\":[";

        bool first = true;

        if (start < filtered.size()) {
            for (size_t index = start; index < end; ++index) {
                if (!first) {
                    body << ",";
                }

                body << filtered[index].toJson();
                first = false;
            }
        }

        const int total =
            static_cast<int>(filtered.size());

        const int pages =
            total == 0
                ? 0
                : (total + limit - 1) / limit;

        body << "],"
             << "\"pagination\":{"
             << "\"page\":" << page << ","
             << "\"limit\":" << limit << ","
             << "\"total\":" << total << ","
             << "\"pages\":" << pages
             << "}}";

        HttpResponse response;
        response.statusCode = 200;
        response.headers["Content-Type"] =
            "application/json";
        response.body = body.str();

        return response;
    }

    HttpResponse patchProduct(
        int id,
        const map<string, string>& body) {
        const set<string> allowedFields{
            "name",
            "category",
            "price",
            "stock",
            "active"
        };

        for (const auto& [field, value] : body) {
            if (!allowedFields.count(field)) {
                return errorResponse(
                    400,
                    "UNKNOWN_FIELD",
                    "Unknown field: " + field
                );
            }
        }

        optional<string> name;
        optional<string> category;
        optional<double> price;
        optional<int> stock;
        optional<bool> active;

        try {
            if (body.count("name")) {
                name = trim(body.at("name"));

                if (name->empty()) {
                    throw ValidationException(
                        "name must not be empty"
                    );
                }
            }

            if (body.count("category")) {
                category = trim(body.at("category"));

                if (category->empty()) {
                    throw ValidationException(
                        "category must not be empty"
                    );
                }
            }

            if (body.count("price")) {
                price =
                    parseNonNegativeDouble(body, "price");
            }

            if (body.count("stock")) {
                stock =
                    parseNonNegativeInt(body, "stock");
            }

            if (body.count("active")) {
                const string value =
                    trim(body.at("active"));

                if (value == "true") {
                    active = true;
                } else if (value == "false") {
                    active = false;
                } else {
                    throw ValidationException(
                        "active must be true or false"
                    );
                }
            }
        } catch (const ValidationException& exception) {
            return errorResponse(
                422,
                "VALIDATION_ERROR",
                exception.what()
            );
        }

        if (!repository.patch(
                id,
                name,
                category,
                price,
                stock,
                active)) {
            return errorResponse(
                404,
                "PRODUCT_NOT_FOUND",
                "Product does not exist"
            );
        }

        return getProduct(id);
    }

    HttpResponse deleteProduct(int id) {
        if (!repository.erase(id)) {
            return errorResponse(
                404,
                "PRODUCT_NOT_FOUND",
                "Product does not exist"
            );
        }

        HttpResponse response;
        response.statusCode = 204;
        return response;
    }
};

// =============================================================================
// Authentication and authorization
// =============================================================================

struct Identity {
    int userId{};
    string role;
};

class AuthenticationService {
private:
    unordered_map<string, Identity> tokens{
        {"token-customer", {1, "customer"}},
        {"token-admin", {2, "admin"}}
    };

public:
    optional<Identity> authenticate(
        const HttpRequest& request) const {
        const auto iterator =
            request.headers.find("Authorization");

        if (iterator == request.headers.end()) {
            return nullopt;
        }

        const string prefix = "Bearer ";

        if (iterator->second.rfind(prefix, 0) != 0) {
            return nullopt;
        }

        const string token =
            iterator->second.substr(prefix.size());

        const auto tokenIterator =
            tokens.find(token);

        if (tokenIterator == tokens.end()) {
            return nullopt;
        }

        return tokenIterator->second;
    }
};

class AuthorizationService {
private:
    map<string, set<string>> permissions{
        {
            "customer",
            {"GET_PRODUCT"}
        },
        {
            "admin",
            {
                "GET_PRODUCT",
                "CREATE_PRODUCT",
                "UPDATE_PRODUCT",
                "DELETE_PRODUCT"
            }
        }
    };

public:
    bool allowed(
        const Identity& identity,
        const string& permission) const {
        const auto iterator =
            permissions.find(identity.role);

        if (iterator == permissions.end()) {
            return false;
        }

        return iterator->second.count(permission) > 0;
    }
};

// =============================================================================
// Rate limiter
// =============================================================================

class FixedWindowRateLimiter {
private:
    struct Record {
        size_t count{};
        chrono::steady_clock::time_point startedAt;
    };

    size_t limit;
    chrono::seconds window;
    unordered_map<string, Record> clients;

public:
    FixedWindowRateLimiter(
        size_t limit,
        chrono::seconds window)
        : limit(limit), window(window) {}

    bool allow(const string& clientId) {
        const auto now =
            chrono::steady_clock::now();

        auto iterator =
            clients.find(clientId);

        if (iterator == clients.end() ||
            now - iterator->second.startedAt >= window) {
            clients[clientId] =
                Record{0, now};

            iterator = clients.find(clientId);
        }

        if (iterator->second.count >= limit) {
            return false;
        }

        ++iterator->second.count;
        return true;
    }
};

// =============================================================================
// Request router
// =============================================================================

class Router {
private:
    using Handler =
        function<HttpResponse(
            const HttpRequest&,
            const smatch&)>;

    struct Route {
        HttpMethod method;
        regex pattern;
        Handler handler;
    };

    vector<Route> routes;

public:
    void add(
        HttpMethod method,
        const string& pattern,
        Handler handler) {
        routes.push_back({
            method,
            regex(pattern),
            move(handler)
        });
    }

    HttpResponse dispatch(
        const HttpRequest& request) const {
        for (const Route& route : routes) {
            if (route.method != request.method) {
                continue;
            }

            smatch match;

            if (regex_match(
                    request.path,
                    match,
                    route.pattern)) {
                return route.handler(
                    request,
                    match
                );
            }
        }

        HttpResponse response;
        response.statusCode = 404;
        response.headers["Content-Type"] =
            "application/json";
        response.body =
            "{"
            "\"error\":{"
            "\"code\":\"ROUTE_NOT_FOUND\","
            "\"message\":\"No matching endpoint\""
            "}"
            "}";

        return response;
    }
};

// =============================================================================
// API Gateway simulation
// =============================================================================

class ApiGateway {
private:
    ProductApi api;
    AuthenticationService authentication;
    AuthorizationService authorization;
    FixedWindowRateLimiter rateLimiter;

    static HttpResponse unauthorized() {
        HttpResponse response;
        response.statusCode = 401;
        response.headers["WWW-Authenticate"] =
            "Bearer";
        response.body =
            "{"
            "\"error\":{"
            "\"code\":\"UNAUTHENTICATED\","
            "\"message\":\"Valid authentication is required\""
            "}"
            "}";
        return response;
    }

    static HttpResponse forbidden() {
        HttpResponse response;
        response.statusCode = 403;
        response.body =
            "{"
            "\"error\":{"
            "\"code\":\"FORBIDDEN\","
            "\"message\":\"Operation is not permitted\""
            "}"
            "}";
        return response;
    }

    static int extractId(
        const smatch& match) {
        return stoi(match[1].str());
    }

public:
    ApiGateway()
        : rateLimiter(
            10,
            chrono::seconds(60)) {}

    ProductApi& productApi() {
        return api;
    }

    HttpResponse handle(
        const string& clientId,
        const HttpRequest& request) {
        if (!rateLimiter.allow(clientId)) {
            HttpResponse response;
            response.statusCode = 429;
            response.body =
                "{"
                "\"error\":{"
                "\"code\":\"RATE_LIMITED\","
                "\"message\":\"Too many requests\""
                "}"
                "}";
            return response;
        }

        const bool requiresAuthentication =
            request.method != HttpMethod::GET;

        optional<Identity> identity =
            authentication.authenticate(request);

        if (requiresAuthentication &&
            !identity.has_value()) {
            return unauthorized();
        }

        if (request.method == HttpMethod::GET) {
            smatch match;

            if (regex_match(
                    request.path,
                    match,
                    regex(R"(^/api/v1/products/([0-9]+)$)"))) {
                return api.getProduct(extractId(match));
            }

            if (request.path ==
                "/api/v1/products") {
                return api.listProducts();
            }
        }

        if (request.method == HttpMethod::POST &&
            request.path ==
                "/api/v1/products") {
            if (!identity.has_value() ||
                !authorization.allowed(
                    *identity,
                    "CREATE_PRODUCT")) {
                return forbidden();
            }

            return api.createProduct(request);
        }

        smatch match;

        if (request.method == HttpMethod::PATCH &&
            regex_match(
                request.path,
                match,
                regex(R"(^/api/v1/products/([0-9]+)$)"))) {
            if (!identity.has_value() ||
                !authorization.allowed(
                    *identity,
                    "UPDATE_PRODUCT")) {
                return forbidden();
            }

            return api.patchProduct(
                extractId(match),
                request.body
            );
        }

        if (request.method ==
                HttpMethod::DELETE_METHOD &&
            regex_match(
                request.path,
                match,
                regex(R"(^/api/v1/products/([0-9]+)$)"))) {
            if (!identity.has_value() ||
                !authorization.allowed(
                    *identity,
                    "DELETE_PRODUCT")) {
                return forbidden();
            }

            return api.deleteProduct(
                extractId(match)
            );
        }

        HttpResponse response;
        response.statusCode = 404;
        response.body =
            "{\"error\":{\"code\":\"ROUTE_NOT_FOUND\"}}";
        return response;
    }
};

// =============================================================================
// Test helpers
// =============================================================================

void assertStatus(
    const HttpResponse& response,
    int expected) {
    if (response.statusCode != expected) {
        throw runtime_error(
            "Expected HTTP " +
            to_string(expected) +
            " but received HTTP " +
            to_string(response.statusCode)
        );
    }
}

// =============================================================================
// Case study
// =============================================================================

void runCaseStudy() {
    section(
        "Industry Case Study: Product Catalog REST API"
    );

    /*
     * The simulated architecture contains:
     *
     * Client
     *   |
     *   v
     * API Gateway
     *   |
     *   +-- Authentication
     *   +-- Authorization
     *   +-- Rate Limiting
     *   |
     *   v
     * Product API
     *   |
     *   v
     * Repository
     *
     * The implementation keeps HTTP transport abstract so the focus remains
     * on resource-oriented architecture and REST semantics.
     */

    ApiGateway gateway;

    HttpRequest createRequest{
        HttpMethod::POST,
        "/api/v1/products",
        {
            {"Authorization", "Bearer token-admin"},
            {"Content-Type", "application/json"}
        },
        {},
        {
            {"name", "Mechanical Keyboard"},
            {"category", "electronics"},
            {"price", "3499"},
            {"stock", "25"}
        }
    };

    cout << "\nPOST /api/v1/products\n";
    HttpResponse createResponse =
        gateway.handle(
            "client-001",
            createRequest
        );

    createResponse.print();
    assertStatus(createResponse, 201);

    cout << "\nGET /api/v1/products\n";

    HttpRequest listRequest{
        HttpMethod::GET,
        "/api/v1/products"
    };

    HttpResponse listResponse =
        gateway.handle(
            "client-001",
            listRequest
        );

    listResponse.print();
    assertStatus(listResponse, 200);

    /*
     * The first product created receives ID 1 in this isolated application.
     */
    cout << "\nGET /api/v1/products/1\n";

    HttpRequest getRequest{
        HttpMethod::GET,
        "/api/v1/products/1"
    };

    HttpResponse getResponse =
        gateway.handle(
            "client-001",
            getRequest
        );

    getResponse.print();
    assertStatus(getResponse, 200);

    cout << "\nPATCH /api/v1/products/1\n";

    HttpRequest patchRequest{
        HttpMethod::PATCH,
        "/api/v1/products/1",
        {
            {"Authorization", "Bearer token-admin"},
            {"Content-Type", "application/json"}
        },
        {},
        {
            {"price", "3299"},
            {"stock", "30"}
        }
    };

    HttpResponse patchResponse =
        gateway.handle(
            "client-001",
            patchRequest
        );

    patchResponse.print();
    assertStatus(patchResponse, 200);

    cout << "\nGET /api/v1/products/999\n";

    HttpRequest missingRequest{
        HttpMethod::GET,
        "/api/v1/products/999"
    };

    HttpResponse missingResponse =
        gateway.handle(
            "client-001",
            missingRequest
        );

    missingResponse.print();
    assertStatus(missingResponse, 404);

    cout << "\nPOST without authentication\n";

    HttpRequest unauthenticatedCreate{
        HttpMethod::POST,
        "/api/v1/products",
        {},
        {},
        {
            {"name", "Unauthorized Product"},
            {"category", "test"},
            {"price", "100"},
            {"stock", "1"}
        }
    };

    HttpResponse unauthorizedResponse =
        gateway.handle(
            "client-002",
            unauthenticatedCreate
        );

    unauthorizedResponse.print();
    assertStatus(unauthorizedResponse, 401);

    cout << "\nDELETE /api/v1/products/1\n";

    HttpRequest deleteRequest{
        HttpMethod::DELETE_METHOD,
        "/api/v1/products/1",
        {
            {"Authorization", "Bearer token-admin"}
        }
    };

    HttpResponse deleteResponse =
        gateway.handle(
            "client-001",
            deleteRequest
        );

    deleteResponse.print();
    assertStatus(deleteResponse, 204);

    cout << "\nGET /api/v1/products/1 after deletion\n";

    HttpResponse deletedGetResponse =
        gateway.handle(
            "client-001",
            getRequest
        );

    deletedGetResponse.print();
    assertStatus(deletedGetResponse, 404);
}

// =============================================================================
// Concept demonstrations
// =============================================================================

void demonstrateRESTConcepts() {
    section("REST architectural concepts");

    cout << "Resource: a conceptual product exposed by the API.\n";
    cout << "Endpoint: an HTTP method combined with a URI pattern.\n";
    cout << "Representation: JSON representation of a product.\n";
    cout << "Statelessness: each request contains its required context.\n";
    cout << "Uniform interface: HTTP methods and resource identifiers provide "
            "standard interaction semantics.\n";
    cout << "Layered architecture: gateways, services, and repositories may "
            "operate as separate layers.\n";
    cout << "Cacheability: responses can communicate cache policy through "
            "HTTP headers.\n";
}

void demonstrateMethods() {
    section("HTTP method semantics");

    cout << left
         << setw(12) << "Method"
         << setw(28) << "Typical meaning"
         << setw(14) << "Safe"
         << setw(16) << "Idempotent"
         << "\n";

    cout << string(70, '-') << "\n";

    cout << setw(12) << "GET"
         << setw(28) << "Retrieve"
         << setw(14) << "Yes"
         << setw(16) << "Yes"
         << "\n";

    cout << setw(12) << "POST"
         << setw(28) << "Create/process"
         << setw(14) << "No"
         << setw(16) << "Usually no"
         << "\n";

    cout << setw(12) << "PUT"
         << setw(28) << "Replace"
         << setw(14) << "No"
         << setw(16) << "Yes"
         << "\n";

    cout << setw(12) << "PATCH"
         << setw(28) << "Partial update"
         << setw(14) << "No"
         << setw(16) << "Depends"
         << "\n";

    cout << setw(12) << "DELETE"
         << setw(28) << "Remove"
         << setw(14) << "No"
         << setw(16) << "Yes"
         << "\n";
}

void demonstrateTradeoffs() {
    section("Design trade-offs");

    cout << "Offset pagination:\n";
    cout << "  Simple client model, but large offsets can become expensive.\n";

    cout << "\nCursor pagination:\n";
    cout << "  Better for large or changing datasets, but requires more state in "
            "the cursor protocol.\n";

    cout << "\nNested resources:\n";
    cout << "  /users/7/orders/22 clearly expresses a relationship, but deep "
            "nesting can become difficult to manage.\n";

    cout << "\nFlat resources:\n";
    cout << "  /orders/22 directly addresses an order, while relationships can "
            "be represented through links or fields.\n";
}

void demonstratePerformance() {
    section("Performance considerations");

    cout << "Repository lookup uses std::map and is approximately O(log n).\n";
    cout << "Listing all products is O(n).\n";
    cout << "Filtering a vector of n products is O(n).\n";
    cout << "Pagination after filtering is O(n) for the in-memory model.\n";
    cout << "Production databases should use suitable indexes and query plans.\n";
    cout << "Network latency, serialization, database I/O, connection pools, "
            "caching, and downstream services can dominate API latency.\n";
}

void demonstrateSecurity() {
    section("Security considerations");

    cout << "1. Use HTTPS/TLS for sensitive API traffic.\n";
    cout << "2. Authenticate protected requests.\n";
    cout << "3. Authorize every sensitive resource operation.\n";
    cout << "4. Validate identifiers and request bodies.\n";
    cout << "5. Apply rate limiting where abuse is possible.\n";
    cout << "6. Avoid returning internal implementation details in errors.\n";
    cout << "7. Verify resource ownership in multi-user applications.\n";
    cout << "8. Protect credentials, tokens, and encryption keys.\n";
    cout << "9. Record appropriate security and audit events.\n";
}

void demonstrateEdgeCases() {
    section("Edge cases");

    ProductApi api;

    HttpRequest invalidRequest{
        HttpMethod::POST,
        "/api/v1/products",
        {},
        {},
        {
            {"name", ""},
            {"category", "electronics"},
            {"price", "-50"},
            {"stock", "-1"}
        }
    };

    HttpResponse invalidResponse =
        api.createProduct(invalidRequest);

    cout << "Invalid product request:\n";
    invalidResponse.print();

    assertStatus(invalidResponse, 422);

    HttpResponse missing =
        api.getProduct(999999);

    cout << "\nMissing product:\n";
    missing.print();

    assertStatus(missing, 404);

    HttpResponse invalidPagination =
        api.listProducts(
            nullopt,
            nullopt,
            nullopt,
            0,
            200
        );

    cout << "\nInvalid pagination:\n";
    invalidPagination.print();

    assertStatus(invalidPagination, 400);
}

// =============================================================================
// Main
// =============================================================================

int main() {
    try {
        demonstrateRESTConcepts();
        demonstrateMethods();
        runCaseStudy();
        demonstrateTradeoffs();
        demonstratePerformance();
        demonstrateSecurity();
        demonstrateEdgeCases();

        section("Case study validation");
        cout << "All critical assertions passed.\n";
        cout << "The simulated REST architecture completed successfully.\n";

        return 0;
    } catch (const exception& exception) {
        cerr << "Fatal error: "
             << exception.what()
             << "\n";

        return 1;
    }
}
