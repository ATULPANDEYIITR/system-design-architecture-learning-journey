/*
 * Web Architecture, Client-Server Architecture, and the Browser
 * Request-Response Lifecycle
 *
 * C++17 case study:
 * A miniature e-commerce API gateway and application server model.
 *
 * The program models:
 * - HTTP requests and responses
 * - routing
 * - query/path processing
 * - validation
 * - authentication
 * - authorization
 * - sessions
 * - caching
 * - ETags
 * - rate limiting
 * - application services
 * - concurrency
 * - error handling
 * - performance considerations
 *
 * This is an architectural simulation rather than a replacement for a
 * production HTTP library or web framework.
 *
 * Compile:
 *     g++ -std=c++17 -O2 -pthread web_architecture.cpp -o web_architecture
 *
 * Run:
 *     ./web_architecture
 */

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std;

// ============================================================================
// 1. BASIC DATA MODELS
// ============================================================================

struct HTTPRequest {
    string method;
    string target;
    map<string, string> headers;
    string body;
};

struct HTTPResponse {
    int statusCode;
    string reason;
    map<string, string> headers;
    string body;
};

void printSection(const string& title) {
    cout << "\n" << string(78, '=') << "\n";
    cout << title << "\n";
    cout << string(78, '=') << "\n";
}

void printResponse(const HTTPResponse& response) {
    cout << response.statusCode << " " << response.reason << "\n";

    for (const auto& [name, value] : response.headers) {
        cout << name << ": " << value << "\n";
    }

    cout << "Body: " << response.body << "\n";
}

// ============================================================================
// 2. URL PARSING
// ============================================================================

struct ParsedURL {
    string scheme;
    string authority;
    string path;
    string query;
    string fragment;
};

ParsedURL parseURL(const string& url) {
    ParsedURL result;

    const size_t schemePosition = url.find("://");

    if (schemePosition == string::npos) {
        throw invalid_argument("URL does not contain a valid scheme");
    }

    result.scheme = url.substr(0, schemePosition);

    const size_t authorityStart = schemePosition + 3;
    const size_t pathStart = url.find('/', authorityStart);
    const size_t queryStart = url.find('?', authorityStart);
    const size_t fragmentStart = url.find('#', authorityStart);

    size_t authorityEnd = url.size();

    for (size_t position : {
             pathStart == string::npos ? url.size() : pathStart,
             queryStart == string::npos ? url.size() : queryStart,
             fragmentStart == string::npos ? url.size() : fragmentStart
         }) {
        authorityEnd = min(authorityEnd, position);
    }

    result.authority = url.substr(
        authorityStart,
        authorityEnd - authorityStart
    );

    const size_t pathEndCandidates[] = {
        queryStart == string::npos ? url.size() : queryStart,
        fragmentStart == string::npos ? url.size() : fragmentStart
    };

    const size_t pathEnd = min(pathEndCandidates[0], pathEndCandidates[1]);

    if (pathStart != string::npos && pathStart < pathEnd) {
        result.path = url.substr(pathStart, pathEnd - pathStart);
    } else {
        result.path = "/";
    }

    if (queryStart != string::npos) {
        const size_t queryEnd =
            fragmentStart == string::npos ? url.size() : fragmentStart;

        result.query = url.substr(
            queryStart + 1,
            queryEnd - queryStart - 1
        );
    }

    if (fragmentStart != string::npos) {
        result.fragment = url.substr(fragmentStart + 1);
    }

    return result;
}

void demonstrateURL() {
    printSection("1. URL anatomy");

    const string url =
        "https://shop.example:443/products/42?currency=INR#details";

    const ParsedURL parsed = parseURL(url);

    cout << "URL      : " << url << "\n";
    cout << "Scheme   : " << parsed.scheme << "\n";
    cout << "Authority: " << parsed.authority << "\n";
    cout << "Path     : " << parsed.path << "\n";
    cout << "Query    : " << parsed.query << "\n";
    cout << "Fragment : " << parsed.fragment << "\n";

    cout << "\nThe fragment identifies client-side document state and is normally "
            "not transmitted to the server as part of the HTTP request target.\n";
}

// ============================================================================
// 3. STATUS AND ERROR FACTORY
// ============================================================================

HTTPResponse jsonResponse(
    int status,
    string reason,
    string body
) {
    return {
        status,
        move(reason),
        {
            {"Content-Type", "application/json"},
            {"X-Content-Type-Options", "nosniff"}
        },
        move(body)
    };
}

// ============================================================================
// 4. APPLICATION DATA
// ============================================================================

struct Product {
    int id;
    string name;
    double price;
    int stock;
};

struct User {
    int id;
    string username;
    string role;
};

class ProductRepository {
private:
    unordered_map<int, Product> products;

public:
    ProductRepository() {
        products.emplace(
            1,
            Product{1, "Keyboard", 2499.00, 20}
        );

        products.emplace(
            2,
            Product{2, "Monitor", 15999.00, 8}
        );

        products.emplace(
            3,
            Product{3, "Mouse", 999.00, 50}
        );
    }

    optional<Product> findById(int id) const {
        const auto iterator = products.find(id);

        if (iterator == products.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    bool reserve(int id, int quantity) {
        if (quantity <= 0) {
            return false;
        }

        auto iterator = products.find(id);

        if (iterator == products.end()) {
            return false;
        }

        if (iterator->second.stock < quantity) {
            return false;
        }

        iterator->second.stock -= quantity;
        return true;
    }
};

// ============================================================================
// 5. SESSION STORE
// ============================================================================

class SessionStore {
private:
    unordered_map<string, User> sessions;
    mutable mutex mutex_;

    string generateSessionId() {
        static random_device randomDevice;
        static mt19937_64 generator(randomDevice());

        uint64_t first = generator();
        uint64_t second = generator();

        stringstream stream;
        stream << hex << first << second;

        return stream.str();
    }

public:
    string create(const User& user) {
        const string sessionId = generateSessionId();

        lock_guard<mutex> lock(mutex_);
        sessions[sessionId] = user;

        return sessionId;
    }

    optional<User> get(const string& sessionId) const {
        lock_guard<mutex> lock(mutex_);

        const auto iterator = sessions.find(sessionId);

        if (iterator == sessions.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    void erase(const string& sessionId) {
        lock_guard<mutex> lock(mutex_);
        sessions.erase(sessionId);
    }
};

// ============================================================================
// 6. SIMPLE CACHE
// ============================================================================

struct CacheEntry {
    HTTPResponse response;
    chrono::steady_clock::time_point expiresAt;
};

class ResponseCache {
private:
    unordered_map<string, CacheEntry> entries;
    mutable mutex mutex_;

public:
    void put(
        const string& key,
        const HTTPResponse& response,
        chrono::seconds ttl
    ) {
        lock_guard<mutex> lock(mutex_);

        entries[key] = CacheEntry{
            response,
            chrono::steady_clock::now() + ttl
        };
    }

    optional<HTTPResponse> get(const string& key) const {
        lock_guard<mutex> lock(mutex_);

        const auto iterator = entries.find(key);

        if (iterator == entries.end()) {
            return nullopt;
        }

        if (chrono::steady_clock::now() >= iterator->second.expiresAt) {
            return nullopt;
        }

        return iterator->second.response;
    }
};

// ============================================================================
// 7. RATE LIMITER
// ============================================================================

class RateLimiter {
private:
    struct ClientState {
        int requests = 0;
        chrono::steady_clock::time_point windowStart =
            chrono::steady_clock::now();
    };

    unordered_map<string, ClientState> clients;
    mutable mutex mutex_;

    const int maximumRequests;
    const chrono::seconds window;

public:
    RateLimiter(
        int maximumRequests_,
        chrono::seconds window_
    )
        : maximumRequests(maximumRequests_),
          window(window_) {}

    bool allow(const string& clientId) {
        lock_guard<mutex> lock(mutex_);

        ClientState& state = clients[clientId];

        const auto now = chrono::steady_clock::now();

        if (now - state.windowStart >= window) {
            state.windowStart = now;
            state.requests = 0;
        }

        if (state.requests >= maximumRequests) {
            return false;
        }

        ++state.requests;
        return true;
    }
};

// ============================================================================
// 8. APPLICATION SERVICE
// ============================================================================

class ProductService {
private:
    ProductRepository& repository;

public:
    explicit ProductService(ProductRepository& repository_)
        : repository(repository_) {}

    optional<Product> getProduct(int id) const {
        return repository.findById(id);
    }

    bool reserveStock(int id, int quantity) {
        return repository.reserve(id, quantity);
    }
};

// ============================================================================
// 9. AUTHORIZATION
// ============================================================================

bool canViewInventory(const User& user) {
    return user.role == "admin" || user.role == "employee";
}

bool canReserveProduct(const User& user) {
    return user.role == "admin" ||
           user.role == "employee" ||
           user.role == "customer";
}

// ============================================================================
// 10. ROUTING
// ============================================================================

class Application {
private:
    ProductService& productService;
    SessionStore& sessions;
    ResponseCache& cache;
    RateLimiter& rateLimiter;

    static string extractPath(const string& target) {
        const size_t queryPosition = target.find('?');

        if (queryPosition == string::npos) {
            return target.empty() ? "/" : target;
        }

        return target.substr(0, queryPosition);
    }

    static optional<int> extractProductId(const string& path) {
        const string prefix = "/api/products/";

        if (path.rfind(prefix, 0) != 0) {
            return nullopt;
        }

        const string idPart = path.substr(prefix.size());

        if (idPart.empty()) {
            return nullopt;
        }

        if (!all_of(
                idPart.begin(),
                idPart.end(),
                [](unsigned char character) {
                    return isdigit(character);
                })) {
            return nullopt;
        }

        try {
            return stoi(idPart);
        } catch (...) {
            return nullopt;
        }
    }

    optional<User> authenticate(
        const HTTPRequest& request
    ) const {
        const auto authorization = request.headers.find("Authorization");

        if (authorization == request.headers.end()) {
            return nullopt;
        }

        const string expected = "Bearer employee-demo-token";

        if (authorization->second != expected) {
            return nullopt;
        }

        return User{42, "demo-user", "employee"};
    }

public:
    Application(
        ProductService& productService_,
        SessionStore& sessions_,
        ResponseCache& cache_,
        RateLimiter& rateLimiter_
    )
        : productService(productService_),
          sessions(sessions_),
          cache(cache_),
          rateLimiter(rateLimiter_) {}

    HTTPResponse handle(
        const HTTPRequest& request,
        const string& clientId
    ) {
        if (!rateLimiter.allow(clientId)) {
            return jsonResponse(
                429,
                "Too Many Requests",
                R"({"error":"rate limit exceeded"})"
            );
        }

        const string path = extractPath(request.target);

        if (request.method == "GET" && path == "/api/health") {
            return jsonResponse(
                200,
                "OK",
                R"({"status":"healthy"})"
            );
        }

        if (request.method == "GET" &&
            path.rfind("/api/products/", 0) == 0) {

            const auto productId = extractProductId(path);

            if (!productId.has_value()) {
                return jsonResponse(
                    400,
                    "Bad Request",
                    R"({"error":"product id must be numeric"})"
                );
            }

            const string cacheKey = "product:" + to_string(*productId);

            if (const auto cached = cache.get(cacheKey)) {
                HTTPResponse response = *cached;
                response.headers["X-Cache"] = "HIT";
                return response;
            }

            const auto product =
                productService.getProduct(*productId);

            if (!product.has_value()) {
                return jsonResponse(
                    404,
                    "Not Found",
                    R"({"error":"product not found"})"
                );
            }

            stringstream body;

            body << fixed << setprecision(2)
                 << "{"
                 << "\"id\":" << product->id << ","
                 << "\"name\":\"" << product->name << "\","
                 << "\"price\":" << product->price << ","
                 << "\"stock\":" << product->stock
                 << "}";

            HTTPResponse response = jsonResponse(
                200,
                "OK",
                body.str()
            );

            response.headers["Cache-Control"] = "max-age=30";
            response.headers["ETag"] = "product-" +
                                       to_string(product->id) +
                                       "-stock-" +
                                       to_string(product->stock);

            cache.put(cacheKey, response, chrono::seconds(30));

            return response;
        }

        if (request.method == "POST" &&
            path == "/api/products/reserve") {

            const auto user = authenticate(request);

            if (!user.has_value()) {
                return jsonResponse(
                    401,
                    "Unauthorized",
                    R"({"error":"authentication required"})"
                );
            }

            if (!canReserveProduct(*user)) {
                return jsonResponse(
                    403,
                    "Forbidden",
                    R"({"error":"operation is not permitted"})"
                );
            }

            const size_t separator = request.body.find(',');

            if (separator == string::npos) {
                return jsonResponse(
                    400,
                    "Bad Request",
                    R"({"error":"expected product_id,quantity"})"
                );
            }

            try {
                const int productId =
                    stoi(request.body.substr(0, separator));

                const int quantity =
                    stoi(request.body.substr(separator + 1));

                if (quantity <= 0) {
                    return jsonResponse(
                        422,
                        "Unprocessable Content",
                        R"({"error":"quantity must be positive"})"
                    );
                }

                if (!productService.reserveStock(productId, quantity)) {
                    return jsonResponse(
                        409,
                        "Conflict",
                        R"({"error":"insufficient stock or product does not exist"})"
                    );
                }

                return jsonResponse(
                    200,
                    "OK",
                    R"({"message":"stock reserved"})"
                );
            } catch (...) {
                return jsonResponse(
                    400,
                    "Bad Request",
                    R"({"error":"invalid numeric values"})"
                );
            }
        }

        return jsonResponse(
            404,
            "Not Found",
            R"({"error":"route not found"})"
        );
    }
};

// ============================================================================
// 11. REQUEST PIPELINE
// ============================================================================

HTTPResponse processRequest(
    Application& application,
    HTTPRequest request,
    const string& clientId
) {
    const auto start = chrono::steady_clock::now();

    cout << "\n[REQUEST] "
         << request.method
         << " "
         << request.target
         << "\n";

    HTTPResponse response =
        application.handle(request, clientId);

    const auto end = chrono::steady_clock::now();

    const auto elapsed =
        chrono::duration_cast<chrono::microseconds>(
            end - start
        ).count();

    cout << "[RESPONSE] "
         << response.statusCode
         << " "
         << response.reason
         << " ("
         << elapsed
         << " us)\n";

    return response;
}

// ============================================================================
// 12. CONCURRENT REQUEST TEST
// ============================================================================

void demonstrateConcurrency(Application& application) {
    printSection("Concurrency and multiple clients");

    vector<thread> workers;
    mutex outputMutex;

    for (int clientNumber = 1; clientNumber <= 6; ++clientNumber) {
        workers.emplace_back(
            [&application, &outputMutex, clientNumber]() {
                HTTPRequest request{
                    "GET",
                    "/api/products/1",
                    {
                        {"Accept", "application/json"}
                    },
                    ""
                };

                HTTPResponse response =
                    application.handle(
                        request,
                        "client-" + to_string(clientNumber)
                    );

                lock_guard<mutex> lock(outputMutex);

                cout << "Client "
                     << clientNumber
                     << " received "
                     << response.statusCode
                     << "\n";
            }
        );
    }

    for (thread& worker : workers) {
        worker.join();
    }

    cout << "\nThe shared cache, session store, and rate limiter use mutexes "
            "because concurrent requests can access shared state at the same time.\n";
}

// ============================================================================
// 13. REQUEST LIFECYCLE
// ============================================================================

void demonstrateLifecycle() {
    printSection("Browser request-response lifecycle");

    const vector<string> stages = {
        "1. User enters a URL or activates a link.",
        "2. Browser parses the URL.",
        "3. Browser checks relevant caches and connection state.",
        "4. DNS may resolve the hostname.",
        "5. TCP or another transport connection is established or reused.",
        "6. TLS negotiates HTTPS encryption when HTTPS is used.",
        "7. Browser constructs the HTTP request.",
        "8. Network infrastructure forwards the request.",
        "9. Reverse proxy or web server accepts the connection.",
        "10. Router identifies the application endpoint.",
        "11. Authentication and authorization may run.",
        "12. Input is validated.",
        "13. Application services access data or other services.",
        "14. Application constructs an HTTP response.",
        "15. Server returns status, headers, and body.",
        "16. Browser receives the response.",
        "17. Browser may request additional resources.",
        "18. Browser parses HTML, CSS, and JavaScript.",
        "19. Browser performs layout, painting, and compositing.",
        "20. User sees the resulting interface."
    };

    for (const string& stage : stages) {
        cout << stage << "\n";
    }
}

// ============================================================================
// 14. ARCHITECTURAL TRADE-OFFS
// ============================================================================

void demonstrateTradeoffs() {
    printSection("Architectural trade-offs");

    cout
        << "Monolithic application:\n"
        << "  - One main deployable application.\n"
        << "  - Simpler deployment and local development.\n"
        << "  - Internal components remain strongly connected.\n\n"

        << "Multi-service architecture:\n"
        << "  - Responsibilities are divided across services.\n"
        << "  - Services can be deployed and scaled independently.\n"
        << "  - Network failures, observability, distributed state, and operational\n"
        << "    complexity become more important.\n\n"

        << "Server-side rendering:\n"
        << "  - Server produces HTML for a request.\n"
        << "  - Initial document can contain meaningful content immediately.\n\n"

        << "Client-side application rendering:\n"
        << "  - Browser executes JavaScript to build or update interface state.\n"
        << "  - More application logic can execute on the client.\n\n"

        << "The appropriate architecture depends on requirements rather than\n"
        << "a universal preference.\n";
}

// ============================================================================
// 15. SECURITY
// ============================================================================

void demonstrateSecurity() {
    printSection("Security considerations");

    const vector<string> principles = {
        "Encrypt sensitive network traffic with HTTPS.",
        "Treat request data as untrusted input.",
        "Authenticate users before protected operations.",
        "Perform authorization on the server.",
        "Use parameterized database queries.",
        "Protect state-changing browser requests against CSRF where applicable.",
        "Use secure cookie attributes for sensitive sessions.",
        "Encode output for its destination to reduce XSS risk.",
        "Limit request sizes and expensive operations.",
        "Rate-limit sensitive or abusive endpoints.",
        "Avoid returning internal stack traces to clients.",
        "Do not place secrets in source code or client-side JavaScript."
    };

    for (const string& principle : principles) {
        cout << "- " << principle << "\n";
    }
}

// ============================================================================
// 16. PERFORMANCE
// ============================================================================

void demonstratePerformance() {
    printSection("Performance considerations");

    constexpr size_t itemCount = 1'000'000;

    vector<int> values;
    values.reserve(itemCount);

    for (size_t index = 0; index < itemCount; ++index) {
        values.push_back(static_cast<int>(index));
    }

    unordered_set<int> valueSet;
    valueSet.reserve(itemCount);

    for (int value : values) {
        valueSet.insert(value);
    }

    const int target = static_cast<int>(itemCount - 1);

    auto startList = chrono::steady_clock::now();

    const bool foundInList =
        find(values.begin(), values.end(), target) != values.end();

    auto endList = chrono::steady_clock::now();

    auto startSet = chrono::steady_clock::now();

    const bool foundInSet =
        valueSet.find(target) != valueSet.end();

    auto endSet = chrono::steady_clock::now();

    const auto listTime =
        chrono::duration_cast<chrono::microseconds>(
            endList - startList
        ).count();

    const auto setTime =
        chrono::duration_cast<chrono::microseconds>(
            endSet - startSet
        ).count();

    cout << "Found in vector: " << boolalpha << foundInList << "\n";
    cout << "Found in set   : " << boolalpha << foundInSet << "\n";
    cout << "Vector lookup  : " << listTime << " microseconds\n";
    cout << "Set lookup     : " << setTime << " microseconds\n";

    cout
        << "\nA vector scan is O(n) for arbitrary membership lookup.\n"
        << "An unordered_set has approximately O(1) average lookup behavior,\n"
        << "although hashing, collisions, memory use, and implementation details matter.\n";
}

// ============================================================================
// 17. COMPLETE CASE STUDY
// ============================================================================

void demonstrateCaseStudy() {
    printSection("Complete client-server case study");

    ProductRepository repository;
    ProductService service(repository);
    SessionStore sessions;
    ResponseCache cache;

    RateLimiter limiter(
        100,
        chrono::seconds(1)
    );

    Application application(
        service,
        sessions,
        cache,
        limiter
    );

    HTTPRequest healthRequest{
        "GET",
        "/api/health",
        {
            {"Accept", "application/json"}
        },
        ""
    };

    printResponse(
        processRequest(
            application,
            healthRequest,
            "192.168.1.10"
        )
    );

    HTTPRequest productRequest{
        "GET",
        "/api/products/1",
        {
            {"Accept", "application/json"}
        },
        ""
    };

    printResponse(
        processRequest(
            application,
            productRequest,
            "192.168.1.10"
        )
    );

    cout << "\nRepeating the product request demonstrates the cache:\n";

    printResponse(
        processRequest(
            application,
            productRequest,
            "192.168.1.10"
        )
    );

    HTTPRequest unauthorizedReservation{
        "POST",
        "/api/products/reserve",
        {
            {"Content-Type", "text/plain"}
        },
        "1,2"
    };

    cout << "\nUnauthorized reservation:\n";

    printResponse(
        processRequest(
            application,
            unauthorizedReservation,
            "192.168.1.10"
        )
    );

    HTTPRequest authorizedReservation{
        "POST",
        "/api/products/reserve",
        {
            {"Content-Type", "text/plain"},
            {"Authorization", "Bearer employee-demo-token"}
        },
        "1,2"
    };

    cout << "\nAuthorized reservation:\n";

    printResponse(
        processRequest(
            application,
            authorizedReservation,
            "192.168.1.10"
        )
    );

    HTTPRequest invalidProduct{
        "GET",
        "/api/products/abc",
        {
            {"Accept", "application/json"}
        },
        ""
    };

    cout << "\nInvalid product ID:\n";

    printResponse(
        processRequest(
            application,
            invalidProduct,
            "192.168.1.10"
        )
    );

    HTTPRequest missingProduct{
        "GET",
        "/api/products/99999",
        {
            {"Accept", "application/json"}
        },
        ""
    };

    cout << "\nMissing product:\n";

    printResponse(
        processRequest(
            application,
            missingProduct,
            "192.168.1.10"
        )
    );
}

// ============================================================================
// 18. MAIN
// ============================================================================

int main() {
    try {
        demonstrateURL();

        printSection("HTTP message fundamentals");

        cout
            << "Request = method + target + headers + optional body\n"
            << "Response = status + headers + optional body\n\n"

            << "Common methods:\n"
            << "GET    retrieve\n"
            << "POST   submit/create/process\n"
            << "PUT    replace\n"
            << "PATCH  partially modify\n"
            << "DELETE remove\n\n"

            << "Status families:\n"
            << "2xx successful\n"
            << "3xx redirection\n"
            << "4xx client/request problem\n"
            << "5xx server processing problem\n";

        demonstrateLifecycle();
        demonstrateTradeoffs();
        demonstrateSecurity();
        demonstratePerformance();
        demonstrateCaseStudy();

        /*
         * The concurrency demonstration is intentionally executed after
         * the single-request case study so the output remains easier to read.
         */
        {
            ProductRepository repository;
            ProductService service(repository);
            SessionStore sessions;
            ResponseCache cache;
            RateLimiter limiter(100, chrono::seconds(1));

            Application application(
                service,
                sessions,
                cache,
                limiter
            );

            demonstrateConcurrency(application);
        }

        printSection("Case study completed");

        cout
            << "The program modeled a browser-facing HTTP API from request "
            << "arrival through routing, authentication, authorization, "
            << "business logic, caching, response generation, and concurrent access.\n";

        return 0;
    }
    catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }
}
