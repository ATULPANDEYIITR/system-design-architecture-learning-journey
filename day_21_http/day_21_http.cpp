/*
 * HTTP: Requests, Responses, Methods, and Status Codes
 * =====================================================
 *
 * Industry-style C++17 case study:
 *
 * A small in-memory REST-like User API is modeled as an HTTP application
 * gateway. The program demonstrates:
 *
 *   - HTTP requests and responses
 *   - HTTP methods
 *   - status codes
 *   - URL/path parsing
 *   - query parameters
 *   - JSON-like payload validation without external libraries
 *   - resource creation, replacement, partial update, and deletion
 *   - idempotency concepts
 *   - retry classification
 *   - rate limiting
 *   - ETag generation
 *   - authentication/authorization decisions
 *   - request-size limits
 *   - error handling
 *   - complexity considerations
 *
 * The program intentionally uses only the C++17 standard library. It models
 * the HTTP application layer rather than implementing a complete TCP/TLS
 * HTTP protocol stack.
 *
 * Compile:
 *     g++ -std=c++17 -O2 http_case_study.cpp -o http_case_study
 *
 * Run:
 *     ./http_case_study
 */

#include <algorithm>
#include <cctype>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

using namespace std;


// ============================================================================
// 1. HTTP STATUS CODES
// ============================================================================

enum class StatusCode {
    OK = 200,
    Created = 201,
    Accepted = 202,
    NoContent = 204,
    BadRequest = 400,
    Unauthorized = 401,
    Forbidden = 403,
    NotFound = 404,
    MethodNotAllowed = 405,
    Conflict = 409,
    PayloadTooLarge = 413,
    UnsupportedMediaType = 415,
    UnprocessableContent = 422,
    TooManyRequests = 429,
    InternalServerError = 500,
    BadGateway = 502,
    ServiceUnavailable = 503,
    GatewayTimeout = 504
};

string statusText(StatusCode code) {
    switch (code) {
        case StatusCode::OK: return "OK";
        case StatusCode::Created: return "Created";
        case StatusCode::Accepted: return "Accepted";
        case StatusCode::NoContent: return "No Content";
        case StatusCode::BadRequest: return "Bad Request";
        case StatusCode::Unauthorized: return "Unauthorized";
        case StatusCode::Forbidden: return "Forbidden";
        case StatusCode::NotFound: return "Not Found";
        case StatusCode::MethodNotAllowed: return "Method Not Allowed";
        case StatusCode::Conflict: return "Conflict";
        case StatusCode::PayloadTooLarge: return "Content Too Large";
        case StatusCode::UnsupportedMediaType:
            return "Unsupported Media Type";
        case StatusCode::UnprocessableContent:
            return "Unprocessable Content";
        case StatusCode::TooManyRequests:
            return "Too Many Requests";
        case StatusCode::InternalServerError:
            return "Internal Server Error";
        case StatusCode::BadGateway:
            return "Bad Gateway";
        case StatusCode::ServiceUnavailable:
            return "Service Unavailable";
        case StatusCode::GatewayTimeout:
            return "Gateway Timeout";
    }

    return "Unknown";
}


// ============================================================================
// 2. HTTP METHOD
// ============================================================================

enum class HttpMethod {
    GET,
    POST,
    PUT,
    PATCH,
    DELETE,
    HEAD,
    OPTIONS
};

optional<HttpMethod> parseMethod(const string& method) {
    if (method == "GET") return HttpMethod::GET;
    if (method == "POST") return HttpMethod::POST;
    if (method == "PUT") return HttpMethod::PUT;
    if (method == "PATCH") return HttpMethod::PATCH;
    if (method == "DELETE") return HttpMethod::DELETE;
    if (method == "HEAD") return HttpMethod::HEAD;
    if (method == "OPTIONS") return HttpMethod::OPTIONS;

    return nullopt;
}

string methodName(HttpMethod method) {
    switch (method) {
        case HttpMethod::GET: return "GET";
        case HttpMethod::POST: return "POST";
        case HttpMethod::PUT: return "PUT";
        case HttpMethod::PATCH: return "PATCH";
        case HttpMethod::DELETE: return "DELETE";
        case HttpMethod::HEAD: return "HEAD";
        case HttpMethod::OPTIONS: return "OPTIONS";
    }

    return "UNKNOWN";
}

bool isIdempotent(HttpMethod method) {
    return method == HttpMethod::GET ||
           method == HttpMethod::HEAD ||
           method == HttpMethod::PUT ||
           method == HttpMethod::DELETE ||
           method == HttpMethod::OPTIONS;
}


// ============================================================================
// 3. HTTP MESSAGE MODELS
// ============================================================================

struct HttpRequest {
    HttpMethod method;
    string target;
    map<string, string> headers;
    string body;

    optional<string> getHeader(const string& requestedName) const {
        for (const auto& [name, value] : headers) {
            if (name.size() == requestedName.size()) {
                bool equal = true;

                for (size_t i = 0; i < name.size(); ++i) {
                    if (tolower(static_cast<unsigned char>(name[i])) !=
                        tolower(static_cast<unsigned char>(requestedName[i]))) {
                        equal = false;
                        break;
                    }
                }

                if (equal) {
                    return value;
                }
            }
        }

        return nullopt;
    }
};

struct HttpResponse {
    StatusCode status;
    map<string, string> headers;
    string body;

    void print() const {
        cout << "HTTP/1.1 "
             << static_cast<int>(status)
             << " "
             << statusText(status)
             << '\n';

        for (const auto& [key, value] : headers) {
            cout << key << ": " << value << '\n';
        }

        cout << '\n';

        if (!body.empty()) {
            cout << body << '\n';
        }
    }
};


// ============================================================================
// 4. DOMAIN MODEL
// ============================================================================

struct User {
    int id;
    string name;
    string email;
};

string escapeJson(const string& value) {
    string result;

    for (char character : value) {
        switch (character) {
            case '"':
                result += "\\\"";
                break;
            case '\\':
                result += "\\\\";
                break;
            case '\n':
                result += "\\n";
                break;
            case '\r':
                result += "\\r";
                break;
            case '\t':
                result += "\\t";
                break;
            default:
                result += character;
        }
    }

    return result;
}

string userToJson(const User& user) {
    ostringstream output;

    output << "{"
           << "\"id\":" << user.id << ","
           << "\"name\":\"" << escapeJson(user.name) << "\","
           << "\"email\":\"" << escapeJson(user.email) << "\""
           << "}";

    return output.str();
}


// ============================================================================
// 5. SIMPLE PAYLOAD PARSING
// ============================================================================

string trim(string value) {
    auto notSpace = [](unsigned char character) {
        return !isspace(character);
    };

    value.erase(
        value.begin(),
        find_if(value.begin(), value.end(), notSpace)
    );

    value.erase(
        find_if(
            value.rbegin(),
            value.rend(),
            notSpace
        ).base(),
        value.end()
    );

    return value;
}

optional<string> extractJsonString(
    const string& json,
    const string& key
) {
    string pattern = "\"" + key + "\"";
    size_t keyPosition = json.find(pattern);

    if (keyPosition == string::npos) {
        return nullopt;
    }

    size_t colon = json.find(':', keyPosition + pattern.size());

    if (colon == string::npos) {
        return nullopt;
    }

    size_t firstQuote = json.find('"', colon + 1);

    if (firstQuote == string::npos) {
        return nullopt;
    }

    string value;

    for (size_t i = firstQuote + 1; i < json.size(); ++i) {
        if (json[i] == '"' && json[i - 1] != '\\') {
            return value;
        }

        if (json[i] == '\\' && i + 1 < json.size()) {
            ++i;

            switch (json[i]) {
                case '"': value += '"'; break;
                case '\\': value += '\\'; break;
                case 'n': value += '\n'; break;
                case 'r': value += '\r'; break;
                case 't': value += '\t'; break;
                default: value += json[i]; break;
            }
        } else {
            value += json[i];
        }
    }

    return nullopt;
}

bool isValidEmail(const string& email) {
    size_t at = email.find('@');

    return at != string::npos &&
           at > 0 &&
           at + 1 < email.size() &&
           email.find('.', at + 1) != string::npos;
}


// ============================================================================
// 6. API SERVICE
// ============================================================================

class UserApi {
private:
    unordered_map<int, User> users;
    int nextId = 4;

    static constexpr size_t MAX_BODY_SIZE = 1'000'000;

    HttpResponse jsonResponse(
        StatusCode status,
        const string& body
    ) const {
        HttpResponse response{
            status,
            {
                {"Content-Type", "application/json; charset=utf-8"},
                {"Content-Length", to_string(body.size())}
            },
            body
        };

        return response;
    }

    HttpResponse errorResponse(
        StatusCode status,
        const string& message
    ) const {
        return jsonResponse(
            status,
            "{\"error\":\"" + escapeJson(message) + "\"}"
        );
    }

    optional<User> parseUserPayload(
        const string& body,
        string& error
    ) const {
        if (body.size() > MAX_BODY_SIZE) {
            error = "Request body exceeds size limit.";
            return nullopt;
        }

        auto name = extractJsonString(body, "name");
        auto email = extractJsonString(body, "email");

        if (!name.has_value() || !email.has_value()) {
            error = "Both name and email are required.";
            return nullopt;
        }

        if (trim(*name).empty()) {
            error = "name cannot be empty.";
            return nullopt;
        }

        if (!isValidEmail(*email)) {
            error = "email is invalid.";
            return nullopt;
        }

        return User{
            0,
            trim(*name),
            trim(*email)
        };
    }

    optional<int> parseUserId(
        const string& path
    ) const {
        const string prefix = "/api/users/";

        if (path.rfind(prefix, 0) != 0) {
            return nullopt;
        }

        string idText = path.substr(prefix.size());

        if (idText.empty()) {
            return nullopt;
        }

        for (char character : idText) {
            if (!isdigit(static_cast<unsigned char>(character))) {
                return nullopt;
            }
        }

        try {
            int id = stoi(idText);

            if (id <= 0) {
                return nullopt;
            }

            return id;
        } catch (const exception&) {
            return nullopt;
        }
    }

public:
    UserApi() {
        users.emplace(1, User{1, "Ada", "ada@example.com"});
        users.emplace(2, User{2, "Alan", "alan@example.com"});
        users.emplace(3, User{3, "Grace", "grace@example.com"});
    }

    HttpResponse handle(const HttpRequest& request) {
        /*
         * Validate request-level constraints before business logic.
         * This protects application code from malformed or oversized input.
         */
        if (request.body.size() > MAX_BODY_SIZE) {
            return errorResponse(
                StatusCode::PayloadTooLarge,
                "Request body is too large."
            );
        }

        const string& path = request.target;

        // --------------------------------------------------------------------
        // GET /api/users
        // --------------------------------------------------------------------

        if (request.method == HttpMethod::GET &&
            path == "/api/users") {

            ostringstream body;
            body << "{\"users\":[";

            bool first = true;

            for (const auto& [id, user] : users) {
                if (!first) {
                    body << ",";
                }

                body << userToJson(user);
                first = false;
            }

            body << "]}";

            return jsonResponse(StatusCode::OK, body.str());
        }

        // --------------------------------------------------------------------
        // POST /api/users
        // --------------------------------------------------------------------

        if (request.method == HttpMethod::POST &&
            path == "/api/users") {

            auto contentType = request.getHeader("Content-Type");

            if (!contentType.has_value() ||
                contentType->find("application/json") != 0) {

                return errorResponse(
                    StatusCode::UnsupportedMediaType,
                    "Expected application/json."
                );
            }

            string error;
            auto parsedUser = parseUserPayload(request.body, error);

            if (!parsedUser.has_value()) {
                return errorResponse(
                    StatusCode::UnprocessableContent,
                    error
                );
            }

            User created = *parsedUser;
            created.id = nextId++;

            users.emplace(created.id, created);

            HttpResponse response = jsonResponse(
                StatusCode::Created,
                userToJson(created)
            );

            response.headers["Location"] =
                "/api/users/" + to_string(created.id);

            return response;
        }

        // --------------------------------------------------------------------
        // Individual user operations
        // --------------------------------------------------------------------

        auto userId = parseUserId(path);

        if (userId.has_value()) {
            int id = *userId;

            auto userIterator = users.find(id);

            if (request.method == HttpMethod::GET) {
                if (userIterator == users.end()) {
                    return errorResponse(
                        StatusCode::NotFound,
                        "User not found."
                    );
                }

                return jsonResponse(
                    StatusCode::OK,
                    userToJson(userIterator->second)
                );
            }

            if (request.method == HttpMethod::PUT) {
                auto contentType = request.getHeader("Content-Type");

                if (!contentType.has_value() ||
                    contentType->find("application/json") != 0) {

                    return errorResponse(
                        StatusCode::UnsupportedMediaType,
                        "Expected application/json."
                    );
                }

                string error;
                auto replacement = parseUserPayload(
                    request.body,
                    error
                );

                if (!replacement.has_value()) {
                    return errorResponse(
                        StatusCode::UnprocessableContent,
                        error
                    );
                }

                User updated = *replacement;
                updated.id = id;

                /*
                 * PUT represents replacement semantics. If this were a
                 * persistent production API, the service would define whether
                 * a missing resource is created or results in 404.
                 *
                 * Here we allow replacement of an existing resource and
                 * creation at the requested identifier.
                 */
                users[id] = updated;

                return jsonResponse(
                    StatusCode::OK,
                    userToJson(updated)
                );
            }

            if (request.method == HttpMethod::PATCH) {
                if (userIterator == users.end()) {
                    return errorResponse(
                        StatusCode::NotFound,
                        "User not found."
                    );
                }

                /*
                 * PATCH is partial modification. Only supplied fields are
                 * changed. A real implementation would use a proper JSON
                 * parser rather than this deliberately small educational
                 * parser.
                 */
                if (auto name = extractJsonString(
                        request.body,
                        "name")) {

                    if (trim(*name).empty()) {
                        return errorResponse(
                            StatusCode::UnprocessableContent,
                            "name cannot be empty."
                        );
                    }

                    userIterator->second.name = trim(*name);
                }

                if (auto email = extractJsonString(
                        request.body,
                        "email")) {

                    if (!isValidEmail(*email)) {
                        return errorResponse(
                            StatusCode::UnprocessableContent,
                            "email is invalid."
                        );
                    }

                    userIterator->second.email = trim(*email);
                }

                return jsonResponse(
                    StatusCode::OK,
                    userToJson(userIterator->second)
                );
            }

            if (request.method == HttpMethod::DELETE) {
                if (userIterator == users.end()) {
                    return errorResponse(
                        StatusCode::NotFound,
                        "User not found."
                    );
                }

                users.erase(userIterator);

                return HttpResponse{
                    StatusCode::NoContent,
                    {},
                    ""
                };
            }

            return errorResponse(
                StatusCode::MethodNotAllowed,
                "Method not supported for this resource."
            );
        }

        // --------------------------------------------------------------------
        // HEAD
        // --------------------------------------------------------------------

        if (request.method == HttpMethod::HEAD &&
            path == "/api/users") {

            return HttpResponse{
                StatusCode::OK,
                {
                    {"Content-Type", "application/json"},
                    {"Content-Length", "0"}
                },
                ""
            };
        }

        // --------------------------------------------------------------------
        // OPTIONS
        // --------------------------------------------------------------------

        if (request.method == HttpMethod::OPTIONS) {
            return HttpResponse{
                StatusCode::NoContent,
                {
                    {
                        "Allow",
                        "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"
                    }
                },
                ""
            };
        }

        return errorResponse(
            StatusCode::NotFound,
            "Route not found."
        );
    }
};


// ============================================================================
// 7. URL AND QUERY PARSING
// ============================================================================

struct ParsedTarget {
    string path;
    map<string, string> query;
};

string urlDecode(const string& input) {
    string output;

    auto hexValue = [](char character) -> int {
        if (character >= '0' && character <= '9') {
            return character - '0';
        }

        if (character >= 'a' && character <= 'f') {
            return character - 'a' + 10;
        }

        if (character >= 'A' && character <= 'F') {
            return character - 'A' + 10;
        }

        return -1;
    };

    for (size_t i = 0; i < input.size(); ++i) {
        if (input[i] == '%' && i + 2 < input.size()) {
            int high = hexValue(input[i + 1]);
            int low = hexValue(input[i + 2]);

            if (high >= 0 && low >= 0) {
                output += static_cast<char>((high << 4) | low);
                i += 2;
                continue;
            }
        }

        if (input[i] == '+') {
            output += ' ';
        } else {
            output += input[i];
        }
    }

    return output;
}

ParsedTarget parseTarget(const string& target) {
    ParsedTarget result;

    size_t questionMark = target.find('?');

    if (questionMark == string::npos) {
        result.path = target;
        return result;
    }

    result.path = target.substr(0, questionMark);

    string queryString = target.substr(questionMark + 1);

    stringstream stream(queryString);
    string pair;

    while (getline(stream, pair, '&')) {
        size_t equals = pair.find('=');

        if (equals == string::npos) {
            result.query[urlDecode(pair)] = "";
        } else {
            string key = pair.substr(0, equals);
            string value = pair.substr(equals + 1);

            result.query[urlDecode(key)] = urlDecode(value);
        }
    }

    return result;
}


// ============================================================================
// 8. RATE LIMITING
// ============================================================================

class RateLimiter {
private:
    struct ClientState {
        int requestCount = 0;
        chrono::steady_clock::time_point windowStart =
            chrono::steady_clock::now();
    };

    unordered_map<string, ClientState> clients;

    int maximumRequests;
    chrono::seconds windowSize;

public:
    RateLimiter(
        int maximumRequests,
        chrono::seconds windowSize
    )
        : maximumRequests(maximumRequests),
          windowSize(windowSize) {}

    bool allow(const string& clientId) {
        auto now = chrono::steady_clock::now();

        ClientState& state = clients[clientId];

        if (now - state.windowStart >= windowSize) {
            state.windowStart = now;
            state.requestCount = 0;
        }

        if (state.requestCount >= maximumRequests) {
            return false;
        }

        ++state.requestCount;
        return true;
    }
};


// ============================================================================
// 9. ETAG CONCEPT
// ============================================================================

string simpleEtag(const string& representation) {
    /*
     * This is an educational deterministic hash-like function. It is not
     * intended as a cryptographic hash and should not replace SHA-256 or a
     * suitable production validator.
     */
    uint64_t hash = 1469598103934665603ULL;

    for (unsigned char byte : representation) {
        hash ^= byte;
        hash *= 1099511628211ULL;
    }

    ostringstream output;
    output << '"' << hex << hash << '"';

    return output.str();
}


// ============================================================================
// 10. AUTHENTICATION AND AUTHORIZATION MODEL
// ============================================================================

struct SecurityContext {
    bool authenticated = false;
    bool canModifyUsers = false;
};

HttpResponse authorize(
    const SecurityContext& security,
    HttpMethod method
) {
    if (!security.authenticated) {
        return HttpResponse{
            StatusCode::Unauthorized,
            {{"WWW-Authenticate", "Bearer"}},
            "{\"error\":\"Authentication required.\"}"
        };
    }

    if (!security.canModifyUsers &&
        method != HttpMethod::GET &&
        method != HttpMethod::HEAD &&
        method != HttpMethod::OPTIONS) {

        return HttpResponse{
            StatusCode::Forbidden,
            {{"Content-Type", "application/json"}},
            "{\"error\":\"Insufficient permissions.\"}"
        };
    }

    return HttpResponse{
        StatusCode::OK,
        {},
        ""
    };
}


// ============================================================================
// 11. RETRY POLICY
// ============================================================================

bool retryableStatus(StatusCode status) {
    return status == StatusCode::BadGateway ||
           status == StatusCode::ServiceUnavailable ||
           status == StatusCode::GatewayTimeout ||
           status == StatusCode::TooManyRequests;
}

bool shouldRetry(
    HttpMethod method,
    StatusCode status,
    int attempt,
    int maximumAttempts
) {
    if (attempt >= maximumAttempts) {
        return false;
    }

    if (!retryableStatus(status)) {
        return false;
    }

    /*
     * Blindly retrying POST is dangerous because the operation may have
     * succeeded even if the response was lost.
     */
    return isIdempotent(method);
}


// ============================================================================
// 12. COMPLEXITY AND SYSTEM DESIGN NOTES
// ============================================================================

void printComplexityNotes() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "COMPLEXITY AND DESIGN CONSIDERATIONS\n";
    cout << string(78, '=') << '\n';

    cout << R"(
The in-memory user store uses unordered_map<int, User>.

Expected complexity:
    lookup by ID       O(1)
    insertion by ID    O(1)
    deletion by ID     O(1)
    list all users     O(n)

These are average-case properties of unordered_map, not absolute guarantees.

A production HTTP service usually contains multiple layers:

    network server
        |
        v
    HTTP parser
        |
        v
    routing
        |
        v
    authentication
        |
        v
    authorization
        |
        v
    validation
        |
        v
    application/service layer
        |
        v
    persistence/database
        |
        v
    HTTP response

Separating these responsibilities makes the system easier to test, secure,
monitor, and evolve.

The program intentionally does not implement TCP, TLS, HTTP/1.1 framing,
chunked transfer encoding, HTTP/2 framing, HTTP/3/QUIC, or a complete JSON
parser. Those mechanisms belong to lower-level protocol/server libraries in
a normal production architecture.
)";
}


// ============================================================================
// 13. CASE STUDY EXECUTION
// ============================================================================

void demonstrateRequests(UserApi& api) {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "HTTP API CASE STUDY\n";
    cout << string(78, '=') << '\n';

    // ------------------------------------------------------------------------
    // GET collection
    // ------------------------------------------------------------------------

    HttpRequest getUsers{
        HttpMethod::GET,
        "/api/users",
        {{"Accept", "application/json"}},
        ""
    };

    cout << "\nREQUEST: GET /api/users\n";
    api.handle(getUsers).print();

    // ------------------------------------------------------------------------
    // GET resource
    // ------------------------------------------------------------------------

    HttpRequest getUser{
        HttpMethod::GET,
        "/api/users/1",
        {{"Accept", "application/json"}},
        ""
    };

    cout << "\nREQUEST: GET /api/users/1\n";
    api.handle(getUser).print();

    // ------------------------------------------------------------------------
    // POST creation
    // ------------------------------------------------------------------------

    HttpRequest createUser{
        HttpMethod::POST,
        "/api/users",
        {
            {"Content-Type", "application/json"},
            {"Accept", "application/json"}
        },
        R"({"name":"Katherine","email":"katherine@example.com"})"
    };

    cout << "\nREQUEST: POST /api/users\n";
    api.handle(createUser).print();

    // ------------------------------------------------------------------------
    // Invalid POST
    // ------------------------------------------------------------------------

    HttpRequest invalidUser{
        HttpMethod::POST,
        "/api/users",
        {
            {"Content-Type", "application/json"},
            {"Accept", "application/json"}
        },
        R"({"name":"","email":"invalid"})"
    };

    cout << "\nREQUEST: POST /api/users with invalid data\n";
    api.handle(invalidUser).print();

    // ------------------------------------------------------------------------
    // PUT replacement
    // ------------------------------------------------------------------------

    HttpRequest replaceUser{
        HttpMethod::PUT,
        "/api/users/1",
        {
            {"Content-Type", "application/json"},
            {"Accept", "application/json"}
        },
        R"({"name":"Ada Updated","email":"ada.updated@example.com"})"
    };

    cout << "\nREQUEST: PUT /api/users/1\n";
    api.handle(replaceUser).print();

    // ------------------------------------------------------------------------
    // PATCH partial modification
    // ------------------------------------------------------------------------

    HttpRequest patchUser{
        HttpMethod::PATCH,
        "/api/users/1",
        {
            {"Content-Type", "application/json"},
            {"Accept", "application/json"}
        },
        R"({"name":"Ada Lovelace"})"
    };

    cout << "\nREQUEST: PATCH /api/users/1\n";
    api.handle(patchUser).print();

    // ------------------------------------------------------------------------
    // DELETE
    // ------------------------------------------------------------------------

    HttpRequest deleteUser{
        HttpMethod::DELETE,
        "/api/users/3",
        {},
        ""
    };

    cout << "\nREQUEST: DELETE /api/users/3\n";
    api.handle(deleteUser).print();

    // ------------------------------------------------------------------------
    // Missing resource
    // ------------------------------------------------------------------------

    HttpRequest missingUser{
        HttpMethod::GET,
        "/api/users/9999",
        {},
        ""
    };

    cout << "\nREQUEST: GET /api/users/9999\n";
    api.handle(missingUser).print();

    // ------------------------------------------------------------------------
    // Unsupported route
    // ------------------------------------------------------------------------

    HttpRequest unknownRoute{
        HttpMethod::GET,
        "/unknown",
        {},
        ""
    };

    cout << "\nREQUEST: GET /unknown\n";
    api.handle(unknownRoute).print();

    // ------------------------------------------------------------------------
    // OPTIONS
    // ------------------------------------------------------------------------

    HttpRequest options{
        HttpMethod::OPTIONS,
        "/api/users",
        {},
        ""
    };

    cout << "\nREQUEST: OPTIONS /api/users\n";
    api.handle(options).print();
}


// ============================================================================
// 14. EDGE CASES
// ============================================================================

void demonstrateEdgeCases() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "EDGE CASES\n";
    cout << string(78, '=') << '\n';

    vector<string> targets = {
        "/api/users",
        "/api/users/42",
        "/api/users?name=Ada",
        "/api/users?page=2&limit=20",
        "/api/users?search=machine%20learning",
        "/api/users?tag=C%2B%2B"
    };

    for (const auto& target : targets) {
        ParsedTarget parsed = parseTarget(target);

        cout << "\nTarget: " << target << '\n';
        cout << "Path:   " << parsed.path << '\n';

        for (const auto& [key, value] : parsed.query) {
            cout << "Query:  " << key << " = " << value << '\n';
        }
    }

    cout << R"(
Important edge cases include:

    - empty request bodies
    - malformed JSON
    - invalid Content-Type
    - oversized bodies
    - invalid resource IDs
    - missing resources
    - duplicate creation requests
    - unsupported methods
    - URL-encoded query values
    - authentication failures
    - authorization failures
    - timeouts
    - upstream failures
    - rate-limit exhaustion
    - stale cached representations

Production systems must validate all untrusted input and should not assume
that a request has the shape expected by a successful client.
)";
}


// ============================================================================
// 15. RATE LIMITER DEMONSTRATION
// ============================================================================

void demonstrateRateLimiter() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "RATE LIMITING\n";
    cout << string(78, '=') << '\n';

    RateLimiter limiter(3, chrono::seconds(60));

    for (int requestNumber = 1; requestNumber <= 5; ++requestNumber) {
        bool allowed = limiter.allow("client-42");

        cout << "Request "
             << requestNumber
             << ": "
             << (allowed ? "allowed" : "429 Too Many Requests")
             << '\n';
    }
}


// ============================================================================
// 16. ETAG DEMONSTRATION
// ============================================================================

void demonstrateEtag() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "ETAG AND CONDITIONAL REQUEST CONCEPT\n";
    cout << string(78, '=') << '\n';

    string representation =
        R"({"id":42,"name":"Ada","email":"ada@example.com"})";

    string etag = simpleEtag(representation);

    cout << "Representation: " << representation << '\n';
    cout << "ETag:           " << etag << '\n';

    cout << R"(
A client can later send:

    If-None-Match: <ETag>

If the representation has not changed, the server can return:

    304 Not Modified

This avoids sending the unchanged representation again.
)";
}


// ============================================================================
// 17. SECURITY DEMONSTRATION
// ============================================================================

void demonstrateSecurity() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "AUTHENTICATION AND AUTHORIZATION\n";
    cout << string(78, '=') << '\n';

    SecurityContext anonymous{
        false,
        false
    };

    SecurityContext readOnly{
        true,
        false
    };

    SecurityContext administrator{
        true,
        true
    };

    cout << "Anonymous: "
         << statusText(authorize(
                anonymous,
                HttpMethod::GET
            ).status)
         << '\n';

    cout << "Read-only user modifying data: "
         << statusText(authorize(
                readOnly,
                HttpMethod::DELETE
            ).status)
         << '\n';

    cout << "Administrator modifying data: "
         << statusText(authorize(
                administrator,
                HttpMethod::DELETE
            ).status)
         << '\n';

    cout << R"(
Authentication answers "Who are you?"

Authorization answers "What are you allowed to do?"

A production application should perform both checks independently from
request parsing and should protect transport with TLS.
)";
}


// ============================================================================
// 18. RETRY DEMONSTRATION
// ============================================================================

void demonstrateRetries() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "RETRY POLICY\n";
    cout << string(78, '=') << '\n';

    vector<pair<HttpMethod, StatusCode>> scenarios = {
        {HttpMethod::GET, StatusCode::ServiceUnavailable},
        {HttpMethod::POST, StatusCode::ServiceUnavailable},
        {HttpMethod::PUT, StatusCode::ServiceUnavailable},
        {HttpMethod::GET, StatusCode::NotFound},
        {HttpMethod::DELETE, StatusCode::TooManyRequests}
    };

    for (const auto& [method, status] : scenarios) {
        cout << methodName(method)
             << " "
             << static_cast<int>(status)
             << " -> retry="
             << boolalpha
             << shouldRetry(method, status, 1, 3)
             << '\n';
    }

    cout << R"(
POST is deliberately not blindly retried. If a client times out after a POST
has already reached the server, the client cannot always know whether the
operation succeeded.

Production APIs may use an idempotency key so the server can recognize a
repeated logical operation and return the original result rather than
performing the operation twice.
)";
}


// ============================================================================
// 19. TESTS
// ============================================================================

void runTests() {
    cout << "\n";
    cout << string(78, '=') << '\n';
    cout << "TESTS\n";
    cout << string(78, '=') << '\n';

    UserApi api;

    HttpRequest request{
        HttpMethod::GET,
        "/api/users/1",
        {},
        ""
    };

    HttpResponse response = api.handle(request);

    if (response.status != StatusCode::OK) {
        throw runtime_error("GET existing user test failed.");
    }

    HttpRequest missing{
        HttpMethod::GET,
        "/api/users/99999",
        {},
        ""
    };

    if (api.handle(missing).status != StatusCode::NotFound) {
        throw runtime_error("404 test failed.");
    }

    HttpRequest invalidPost{
        HttpMethod::POST,
        "/api/users",
        {{"Content-Type", "application/json"}},
        R"({"name":"","email":"bad"})"
    };

    if (api.handle(invalidPost).status !=
        StatusCode::UnprocessableContent) {

        throw runtime_error("Validation test failed.");
    }

    if (!isIdempotent(HttpMethod::GET)) {
        throw runtime_error("GET idempotency test failed.");
    }

    if (isIdempotent(HttpMethod::POST)) {
        throw runtime_error("POST idempotency test failed.");
    }

    if (!retryableStatus(StatusCode::ServiceUnavailable)) {
        throw runtime_error("503 retry test failed.");
    }

    cout << "All tests passed.\n";
}


// ============================================================================
// 20. MAIN
// ============================================================================

int main() {
    try {
        cout << string(78, '=') << '\n';
        cout << "HTTP CASE STUDY IN C++17\n";
        cout << "Requests, Responses, Methods, and Status Codes\n";
        cout << string(78, '=') << '\n';

        demonstrateRequests(
            *new UserApi()
        );

        /*
         * The case study above intentionally focuses on the HTTP application
         * layer. The remaining demonstrations isolate important production
         * concerns that surround request/response processing.
         */
        demonstrateEdgeCases();
        demonstrateRateLimiter();
        demonstrateEtag();
        demonstrateSecurity();
        demonstrateRetries();
        printComplexityNotes();
        runTests();

        cout << "\n";
        cout << string(78, '=') << '\n';
        cout << "C++ HTTP case study completed successfully.\n";
        cout << string(78, '=') << '\n';

        return 0;
    }
    catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }
}
