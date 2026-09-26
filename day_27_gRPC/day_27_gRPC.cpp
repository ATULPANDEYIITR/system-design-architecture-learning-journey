/*
 * gRPC, RPC, Protocol Buffers, and Service-to-Service Communication
 * ==================================================================
 *
 * C++ case study:
 *
 * A service-oriented order platform containing:
 *
 *   Client Application
 *          |
 *          v
 *   Dashboard Service
 *       /      \
 *      v        v
 * User Service  Order Service
 *      |           |
 *      v           v
 * User Store   Order Store
 *
 * The implementation is intentionally self-contained and uses the C++17
 * standard library. It models the architectural and behavioral concepts
 * normally implemented by a production gRPC runtime and generated protobuf
 * classes.
 *
 * Compile:
 *   g++ -std=c++17 -O2 -Wall -Wextra -pedantic grpc_case_study.cpp -o grpc_case_study
 *
 * A production gRPC application would normally replace the local transport
 * abstractions with generated code from .proto definitions and an actual
 * gRPC runtime.
 */

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <exception>
#include <functional>
#include <future>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

using namespace std;
using namespace std::chrono_literals;


// ============================================================================
// 1. RPC STATUS
// ============================================================================

enum class RpcStatusCode {
    OK,
    INVALID_ARGUMENT,
    NOT_FOUND,
    DEADLINE_EXCEEDED,
    UNAVAILABLE,
    INTERNAL,
    UNAUTHENTICATED,
    PERMISSION_DENIED
};

string statusToString(RpcStatusCode status) {
    switch (status) {
        case RpcStatusCode::OK:
            return "OK";
        case RpcStatusCode::INVALID_ARGUMENT:
            return "INVALID_ARGUMENT";
        case RpcStatusCode::NOT_FOUND:
            return "NOT_FOUND";
        case RpcStatusCode::DEADLINE_EXCEEDED:
            return "DEADLINE_EXCEEDED";
        case RpcStatusCode::UNAVAILABLE:
            return "UNAVAILABLE";
        case RpcStatusCode::INTERNAL:
            return "INTERNAL";
        case RpcStatusCode::UNAUTHENTICATED:
            return "UNAUTHENTICATED";
        case RpcStatusCode::PERMISSION_DENIED:
            return "PERMISSION_DENIED";
    }

    return "UNKNOWN";
}


class RpcException : public runtime_error {
private:
    RpcStatusCode code_;

public:
    RpcException(
        RpcStatusCode code,
        const string& message
    )
        : runtime_error(message), code_(code) {}

    RpcStatusCode code() const noexcept {
        return code_;
    }
};


// ============================================================================
// 2. PROTOCOL-BUFFER-STYLE MESSAGES
// ============================================================================

struct User {
    int32_t id = 0;
    string name;
    string email;
};

struct GetUserRequest {
    int32_t user_id = 0;
};

struct GetUserResponse {
    bool found = false;
    User user;
    string message;
};

struct Order {
    int64_t order_id = 0;
    int32_t user_id = 0;
    double amount = 0.0;
    string state;
};


/*
 * Conceptual .proto schema:
 *
 * message User {
 *     int32 id = 1;
 *     string name = 2;
 *     string email = 3;
 * }
 *
 * message GetUserRequest {
 *     int32 user_id = 1;
 * }
 *
 * message GetUserResponse {
 *     bool found = 1;
 *     User user = 2;
 *     string message = 3;
 * }
 *
 * service UserService {
 *     rpc GetUser(GetUserRequest) returns (GetUserResponse);
 * }
 *
 * The numeric field tags are part of the wire contract.
 */


// ============================================================================
// 3. RPC METADATA
// ============================================================================

class RpcMetadata {
private:
    map<string, string> values_;

    static string normalizeKey(string key) {
        transform(
            key.begin(),
            key.end(),
            key.begin(),
            [](unsigned char character) {
                return static_cast<char>(
                    tolower(character)
                );
            }
        );

        return key;
    }

public:
    void set(const string& key, const string& value) {
        values_[normalizeKey(key)] = value;
    }

    optional<string> get(const string& key) const {
        const auto normalized = normalizeKey(key);
        const auto iterator = values_.find(normalized);

        if (iterator == values_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    const map<string, string>& values() const {
        return values_;
    }
};


// ============================================================================
// 4. REQUEST CONTEXT
// ============================================================================

struct TraceContext {
    string trace_id;
    string span_id;
    optional<string> parent_span_id;
};

struct RequestContext {
    string request_id;
    TraceContext trace;
    RpcMetadata metadata;
    chrono::steady_clock::time_point deadline;
};


// ============================================================================
// 5. UTILITY FUNCTIONS
// ============================================================================

string generateIdentifier(const string& prefix) {
    static atomic<uint64_t> counter{1};

    ostringstream stream;
    stream << prefix << "-" << counter.fetch_add(1);

    return stream.str();
}

bool deadlineExpired(
    const RequestContext& context
) {
    return chrono::steady_clock::now() >= context.deadline;
}

void ensureDeadline(const RequestContext& context) {
    if (deadlineExpired(context)) {
        throw RpcException(
            RpcStatusCode::DEADLINE_EXCEEDED,
            "RPC deadline exceeded."
        );
    }
}


// ============================================================================
// 6. USER SERVICE
// ============================================================================

class UserService {
private:
    unordered_map<int32_t, User> users_;
    mutable mutex mutex_;

public:
    UserService() {
        users_.emplace(
            1,
            User{1, "Ada", "ada@example.com"}
        );

        users_.emplace(
            2,
            User{2, "Grace", "grace@example.com"}
        );

        users_.emplace(
            3,
            User{3, "Alan", "alan@example.com"}
        );
    }

    GetUserResponse getUser(
        const GetUserRequest& request,
        const RequestContext& context
    ) {
        ensureDeadline(context);

        if (request.user_id <= 0) {
            throw RpcException(
                RpcStatusCode::INVALID_ARGUMENT,
                "user_id must be positive."
            );
        }

        lock_guard<mutex> lock(mutex_);

        const auto iterator = users_.find(request.user_id);

        if (iterator == users_.end()) {
            throw RpcException(
                RpcStatusCode::NOT_FOUND,
                "Requested user does not exist."
            );
        }

        return GetUserResponse{
            true,
            iterator->second,
            "User retrieved successfully."
        };
    }
};


// ============================================================================
// 7. ORDER SERVICE
// ============================================================================

class OrderService {
private:
    vector<Order> orders_;
    mutable mutex mutex_;

public:
    OrderService() {
        orders_.push_back(
            Order{5001, 1, 2499.0, "PAID"}
        );

        orders_.push_back(
            Order{5002, 2, 1299.0, "CREATED"}
        );

        orders_.push_back(
            Order{5003, 1, 5999.0, "SHIPPED"}
        );
    }

    vector<Order> getOrdersForUser(
        int32_t user_id,
        const RequestContext& context
    ) {
        ensureDeadline(context);

        if (user_id <= 0) {
            throw RpcException(
                RpcStatusCode::INVALID_ARGUMENT,
                "user_id must be positive."
            );
        }

        lock_guard<mutex> lock(mutex_);

        vector<Order> result;

        for (const auto& order : orders_) {
            if (order.user_id == user_id) {
                result.push_back(order);
            }
        }

        return result;
    }
};


// ============================================================================
// 8. AUTHORIZATION
// ============================================================================

struct Identity {
    string subject;
    set<string> roles;
};

void requireRole(
    const Identity& identity,
    const string& required_role
) {
    if (
        identity.roles.find(required_role)
        == identity.roles.end()
    ) {
        throw RpcException(
            RpcStatusCode::PERMISSION_DENIED,
            "Required role is missing."
        );
    }
}


// ============================================================================
// 9. SERVICE DISCOVERY AND LOAD BALANCING
// ============================================================================

struct ServiceInstance {
    string address;
    bool healthy = true;
    size_t active_requests = 0;
};

class RoundRobinBalancer {
private:
    vector<shared_ptr<ServiceInstance>> instances_;
    size_t next_index_ = 0;
    mutex mutex_;

public:
    explicit RoundRobinBalancer(
        vector<shared_ptr<ServiceInstance>> instances
    )
        : instances_(move(instances)) {
        if (instances_.empty()) {
            throw invalid_argument(
                "At least one service instance is required."
            );
        }
    }

    shared_ptr<ServiceInstance> choose() {
        lock_guard<mutex> lock(mutex_);

        vector<shared_ptr<ServiceInstance>> healthy;

        for (const auto& instance : instances_) {
            if (instance->healthy) {
                healthy.push_back(instance);
            }
        }

        if (healthy.empty()) {
            throw RpcException(
                RpcStatusCode::UNAVAILABLE,
                "No healthy service instances."
            );
        }

        auto selected =
            healthy[next_index_ % healthy.size()];

        ++next_index_;
        ++selected->active_requests;

        return selected;
    }
};


// ============================================================================
// 10. HEALTH SERVICE
// ============================================================================

enum class HealthState {
    SERVING,
    NOT_SERVING
};

string healthToString(HealthState state) {
    return state == HealthState::SERVING
        ? "SERVING"
        : "NOT_SERVING";
}

class HealthService {
private:
    map<string, HealthState> states_;
    mutable mutex mutex_;

public:
    void setStatus(
        const string& service,
        HealthState state
    ) {
        lock_guard<mutex> lock(mutex_);
        states_[service] = state;
    }

    HealthState check(
        const string& service
    ) const {
        lock_guard<mutex> lock(mutex_);

        const auto iterator = states_.find(service);

        if (iterator == states_.end()) {
            return HealthState::NOT_SERVING;
        }

        return iterator->second;
    }
};


// ============================================================================
// 11. RPC METRICS
// ============================================================================

class RpcMetrics {
private:
    mutable mutex mutex_;
    uint64_t calls_ = 0;
    uint64_t failures_ = 0;
    double total_latency_ms_ = 0.0;

public:
    void record(
        bool success,
        double latency_ms
    ) {
        lock_guard<mutex> lock(mutex_);

        ++calls_;

        if (!success) {
            ++failures_;
        }

        total_latency_ms_ += latency_ms;
    }

    double averageLatencyMs() const {
        lock_guard<mutex> lock(mutex_);

        if (calls_ == 0) {
            return 0.0;
        }

        return total_latency_ms_
            / static_cast<double>(calls_);
    }

    uint64_t calls() const {
        lock_guard<mutex> lock(mutex_);
        return calls_;
    }

    uint64_t failures() const {
        lock_guard<mutex> lock(mutex_);
        return failures_;
    }
};


// ============================================================================
// 12. LOGGING INTERCEPTOR
// ============================================================================

template <typename Function>
auto executeWithMetrics(
    const string& method_name,
    const RequestContext& context,
    RpcMetrics& metrics,
    Function&& function
) -> decltype(function()) {
    const auto started =
        chrono::steady_clock::now();

    cout
        << "  -> "
        << method_name
        << " request="
        << context.request_id
        << "\n";

    try {
        auto result = function();

        const auto finished =
            chrono::steady_clock::now();

        const double latency =
            chrono::duration<double, milli>(
                finished - started
            ).count();

        metrics.record(true, latency);

        cout
            << "  <- "
            << method_name
            << " OK "
            << fixed
            << setprecision(3)
            << latency
            << " ms\n";

        return result;
    }
    catch (...) {
        const auto finished =
            chrono::steady_clock::now();

        const double latency =
            chrono::duration<double, milli>(
                finished - started
            ).count();

        metrics.record(false, latency);

        cout
            << "  <- "
            << method_name
            << " FAILED "
            << fixed
            << setprecision(3)
            << latency
            << " ms\n";

        throw;
    }
}


// ============================================================================
// 13. DASHBOARD SERVICE
// ============================================================================

struct Dashboard {
    User user;
    vector<Order> orders;
    double total_value = 0.0;
};

class DashboardService {
private:
    UserService& user_service_;
    OrderService& order_service_;
    RpcMetrics& metrics_;

public:
    DashboardService(
        UserService& user_service,
        OrderService& order_service,
        RpcMetrics& metrics
    )
        : user_service_(user_service),
          order_service_(order_service),
          metrics_(metrics) {}

    Dashboard getDashboard(
        int32_t user_id,
        const RequestContext& context
    ) {
        ensureDeadline(context);

        GetUserRequest user_request{
            user_id
        };

        auto user_response =
            executeWithMetrics(
                "UserService/GetUser",
                context,
                metrics_,
                [&]() {
                    return user_service_.getUser(
                        user_request,
                        context
                    );
                }
            );

        if (!user_response.found) {
            throw RpcException(
                RpcStatusCode::INTERNAL,
                "User service returned an invalid response."
            );
        }

        auto orders =
            executeWithMetrics(
                "OrderService/GetOrdersForUser",
                context,
                metrics_,
                [&]() {
                    return order_service_.getOrdersForUser(
                        user_id,
                        context
                    );
                }
            );

        double total_value = 0.0;

        for (const auto& order : orders) {
            total_value += order.amount;
        }

        return Dashboard{
            user_response.user,
            move(orders),
            total_value
        };
    }
};


// ============================================================================
// 14. IDEMPOTENCY STORE
// ============================================================================

class IdempotencyStore {
private:
    unordered_map<string, string> results_;
    mutable mutex mutex_;

public:
    optional<string> get(
        const string& key
    ) const {
        lock_guard<mutex> lock(mutex_);

        const auto iterator =
            results_.find(key);

        if (iterator == results_.end()) {
            return nullopt;
        }

        return iterator->second;
    }

    void put(
        const string& key,
        const string& result
    ) {
        lock_guard<mutex> lock(mutex_);
        results_[key] = result;
    }
};


class PaymentService {
private:
    IdempotencyStore store_;
    double total_received_ = 0.0;
    mutable mutex mutex_;

public:
    string charge(
        double amount,
        const string& idempotency_key
    ) {
        if (!isfinite(amount) || amount <= 0.0) {
            throw RpcException(
                RpcStatusCode::INVALID_ARGUMENT,
                "Payment amount must be positive."
            );
        }

        if (idempotency_key.empty()) {
            throw RpcException(
                RpcStatusCode::INVALID_ARGUMENT,
                "Idempotency key is required."
            );
        }

        if (auto existing = store_.get(idempotency_key)) {
            return *existing;
        }

        lock_guard<mutex> lock(mutex_);

        /*
         * The key is checked again under the write lock in a production-grade
         * implementation to prevent concurrent duplicate execution.
         */
        if (auto existing = store_.get(idempotency_key)) {
            return *existing;
        }

        total_received_ += amount;

        const string receipt =
            generateIdentifier("payment");

        store_.put(
            idempotency_key,
            receipt
        );

        return receipt;
    }

    double totalReceived() const {
        lock_guard<mutex> lock(mutex_);
        return total_received_;
    }
};


// ============================================================================
// 15. RETRY POLICY
// ============================================================================

class TemporaryFailure : public runtime_error {
public:
    explicit TemporaryFailure(
        const string& message
    )
        : runtime_error(message) {}
};

template <typename Function>
auto retryWithBackoff(
    Function&& function,
    int attempts,
    chrono::milliseconds initial_delay
) -> decltype(function()) {
    if (attempts <= 0) {
        throw invalid_argument(
            "attempts must be positive."
        );
    }

    auto delay = initial_delay;

    for (int attempt = 1;
         attempt <= attempts;
         ++attempt) {
        try {
            return function();
        }
        catch (const TemporaryFailure&) {
            if (attempt == attempts) {
                throw;
            }

            this_thread::sleep_for(delay);

            delay *= 2;
        }
    }

    throw logic_error("Unreachable.");
}


// ============================================================================
// 16. CIRCUIT BREAKER
// ============================================================================

enum class CircuitState {
    CLOSED,
    OPEN,
    HALF_OPEN
};

class CircuitBreaker {
private:
    CircuitState state_ = CircuitState::CLOSED;
    size_t failures_ = 0;
    size_t threshold_;
    mutable mutex mutex_;

public:
    explicit CircuitBreaker(
        size_t threshold
    )
        : threshold_(threshold) {
        if (threshold_ == 0) {
            throw invalid_argument(
                "Circuit threshold must be positive."
            );
        }
    }

    template <typename Function>
    auto execute(Function&& function)
        -> decltype(function()) {
        {
            lock_guard<mutex> lock(mutex_);

            if (state_ == CircuitState::OPEN) {
                throw RpcException(
                    RpcStatusCode::UNAVAILABLE,
                    "Circuit is open."
                );
            }
        }

        try {
            auto result = function();

            lock_guard<mutex> lock(mutex_);

            failures_ = 0;
            state_ = CircuitState::CLOSED;

            return result;
        }
        catch (const TemporaryFailure&) {
            lock_guard<mutex> lock(mutex_);

            ++failures_;

            if (failures_ >= threshold_) {
                state_ = CircuitState::OPEN;
            }

            throw;
        }
    }

    CircuitState state() const {
        lock_guard<mutex> lock(mutex_);
        return state_;
    }
};


// ============================================================================
// 17. BOUNDED CONCURRENCY / BULKHEAD
// ============================================================================

class Semaphore {
private:
    mutex mutex_;
    condition_variable condition_;
    size_t permits_;

public:
    explicit Semaphore(size_t permits)
        : permits_(permits) {
        if (permits == 0) {
            throw invalid_argument(
                "Semaphore requires at least one permit."
            );
        }
    }

    void acquire() {
        unique_lock<mutex> lock(mutex_);

        condition_.wait(
            lock,
            [&]() {
                return permits_ > 0;
            }
        );

        --permits_;
    }

    void release() {
        {
            lock_guard<mutex> lock(mutex_);
            ++permits_;
        }

        condition_.notify_one();
    }
};


class Bulkhead {
private:
    Semaphore semaphore_;

public:
    explicit Bulkhead(size_t maximum_concurrent)
        : semaphore_(maximum_concurrent) {}

    template <typename Function>
    auto execute(Function&& function)
        -> decltype(function()) {
        semaphore_.acquire();

        try {
            auto result = function();
            semaphore_.release();
            return result;
        }
        catch (...) {
            semaphore_.release();
            throw;
        }
    }
};


// ============================================================================
// 18. STREAMING CONCEPT
// ============================================================================

class NumberStreamService {
public:
    vector<int> serverStreaming(
        int limit
    ) const {
        if (limit < 0) {
            throw RpcException(
                RpcStatusCode::INVALID_ARGUMENT,
                "limit cannot be negative."
            );
        }

        vector<int> results;

        for (int number = 1;
             number <= limit;
             ++number) {
            results.push_back(number * number);
        }

        return results;
    }

    int clientStreaming(
        const vector<int>& values
    ) const {
        long long total = 0;

        for (const int value : values) {
            total += value;
        }

        if (
            total >
            numeric_limits<int>::max()
        ) {
            throw RpcException(
                RpcStatusCode::INTERNAL,
                "Stream sum overflow."
            );
        }

        return static_cast<int>(total);
    }

    vector<int> bidirectionalStreaming(
        const vector<int>& values
    ) const {
        vector<int> results;

        for (const int value : values) {
            results.push_back(value * 10);
        }

        return results;
    }
};


// ============================================================================
// 19. PROTOBUF-STYLE VARINT ENCODING
// ============================================================================

vector<uint8_t> encodeVarint(
    uint64_t value
) {
    vector<uint8_t> bytes;

    while (true) {
        uint8_t current =
            static_cast<uint8_t>(
                value & 0x7F
            );

        value >>= 7;

        if (value != 0) {
            current |= 0x80;
        }

        bytes.push_back(current);

        if (value == 0) {
            return bytes;
        }
    }
}

uint64_t decodeVarint(
    const vector<uint8_t>& data,
    size_t& offset
) {
    uint64_t result = 0;
    unsigned shift = 0;

    while (offset < data.size()) {
        const uint8_t byte =
            data[offset++];

        result |=
            static_cast<uint64_t>(
                byte & 0x7F
            ) << shift;

        if ((byte & 0x80) == 0) {
            return result;
        }

        shift += 7;

        if (shift >= 64) {
            throw invalid_argument(
                "Malformed varint."
            );
        }
    }

    throw invalid_argument(
        "Incomplete varint."
    );
}


// ============================================================================
// 20. SIMPLIFIED PROTOBUF FIELD ENCODING
// ============================================================================

void appendBytes(
    vector<uint8_t>& destination,
    const vector<uint8_t>& source
) {
    destination.insert(
        destination.end(),
        source.begin(),
        source.end()
    );
}

vector<uint8_t> encodeStringField(
    uint32_t field_number,
    const string& value
) {
    if (field_number == 0) {
        throw invalid_argument(
            "Field number must be positive."
        );
    }

    /*
     * Protobuf wire type 2 = length-delimited.
     *
     * Key:
     *     (field_number << 3) | wire_type
     */
    const uint32_t key =
        (field_number << 3) | 2;

    vector<uint8_t> encoded;

    appendBytes(
        encoded,
        encodeVarint(key)
    );

    appendBytes(
        encoded,
        encodeVarint(value.size())
    );

    encoded.insert(
        encoded.end(),
        value.begin(),
        value.end()
    );

    return encoded;
}

vector<uint8_t> encodeIntField(
    uint32_t field_number,
    uint64_t value
) {
    const uint32_t key =
        (field_number << 3);

    vector<uint8_t> encoded =
        encodeVarint(key);

    appendBytes(
        encoded,
        encodeVarint(value)
    );

    return encoded;
}

vector<uint8_t> encodeUser(
    const User& user
) {
    vector<uint8_t> encoded;

    if (user.id != 0) {
        appendBytes(
            encoded,
            encodeIntField(
                1,
                static_cast<uint64_t>(
                    user.id
                )
            )
        );
    }

    if (!user.name.empty()) {
        appendBytes(
            encoded,
            encodeStringField(
                2,
                user.name
            )
        );
    }

    if (!user.email.empty()) {
        appendBytes(
            encoded,
            encodeStringField(
                3,
                user.email
            )
        );
    }

    return encoded;
}


// ============================================================================
// 21. SIMPLE HEX DUMP
// ============================================================================

string bytesToHex(
    const vector<uint8_t>& bytes
) {
    ostringstream stream;

    for (uint8_t byte : bytes) {
        stream
            << hex
            << setw(2)
            << setfill('0')
            << static_cast<unsigned>(byte);
    }

    return stream.str();
}


// ============================================================================
// 22. USER INDEX PERFORMANCE
// ============================================================================

unordered_map<int32_t, User>
buildUserIndex(
    const vector<User>& users
) {
    unordered_map<int32_t, User> index;

    index.reserve(users.size());

    for (const auto& user : users) {
        index.emplace(
            user.id,
            user
        );
    }

    return index;
}


// ============================================================================
// 23. DEADLINE BUDGETING
// ============================================================================

chrono::milliseconds remainingBudget(
    const RequestContext& context
) {
    const auto now =
        chrono::steady_clock::now();

    if (now >= context.deadline) {
        return 0ms;
    }

    return chrono::duration_cast<
        chrono::milliseconds
    >(context.deadline - now);
}


// ============================================================================
// 24. MAIN CASE STUDY
// ============================================================================

int main() {
    cout
        << string(78, '=')
        << "\n"
        << "C++ gRPC SERVICE-TO-SERVICE CASE STUDY\n"
        << string(78, '=')
        << "\n\n";

    try {
        // --------------------------------------------------------------------
        // Create services.
        // --------------------------------------------------------------------

        UserService user_service;
        OrderService order_service;
        RpcMetrics metrics;

        DashboardService dashboard_service(
            user_service,
            order_service,
            metrics
        );

        // --------------------------------------------------------------------
        // Authentication / authorization.
        // --------------------------------------------------------------------

        Identity identity{
            "dashboard-service",
            {"reader", "dashboard"}
        };

        requireRole(
            identity,
            "reader"
        );

        cout
            << "[1] Authorization succeeded for "
            << identity.subject
            << "\n";

        // --------------------------------------------------------------------
        // Build request context.
        // --------------------------------------------------------------------

        RequestContext context{
            generateIdentifier("request"),
            TraceContext{
                generateIdentifier("trace"),
                generateIdentifier("span"),
                nullopt
            },
            RpcMetadata{},
            chrono::steady_clock::now() + 2s
        };

        context.metadata.set(
            "x-request-id",
            context.request_id
        );

        context.metadata.set(
            "x-trace-id",
            context.trace.trace_id
        );

        cout
            << "[2] Request ID: "
            << context.request_id
            << "\n";

        cout
            << "[2] Trace ID: "
            << context.trace.trace_id
            << "\n";

        // --------------------------------------------------------------------
        // Dashboard aggregation.
        // --------------------------------------------------------------------

        Dashboard dashboard =
            dashboard_service.getDashboard(
                1,
                context
            );

        cout
            << "\n[3] Dashboard response\n";

        cout
            << "User: "
            << dashboard.user.name
            << " <"
            << dashboard.user.email
            << ">\n";

        cout
            << "Orders: "
            << dashboard.orders.size()
            << "\n";

        cout
            << "Total order value: "
            << fixed
            << setprecision(2)
            << dashboard.total_value
            << "\n";

        // --------------------------------------------------------------------
        // Error handling.
        // --------------------------------------------------------------------

        cout
            << "\n[4] Missing-user error\n";

        try {
            dashboard_service.getDashboard(
                9999,
                context
            );
        }
        catch (const RpcException& error) {
            cout
                << "Code: "
                << statusToString(error.code())
                << "\n";

            cout
                << "Message: "
                << error.what()
                << "\n";
        }

        // --------------------------------------------------------------------
        // Streaming.
        // --------------------------------------------------------------------

        NumberStreamService stream_service;

        cout
            << "\n[5] Server streaming\n";

        const auto squares =
            stream_service.serverStreaming(5);

        for (const auto value : squares) {
            cout
                << value
                << " ";
        }

        cout << "\n";

        cout
            << "[5] Client streaming result: "
            << stream_service.clientStreaming(
                {1, 2, 3, 4}
            )
            << "\n";

        cout
            << "[5] Bidirectional streaming result: ";

        const auto bidirectional =
            stream_service.bidirectionalStreaming(
                {2, 4, 6}
            );

        for (const auto value : bidirectional) {
            cout
                << value
                << " ";
        }

        cout << "\n";

        // --------------------------------------------------------------------
        // Protocol Buffer wire demonstration.
        // --------------------------------------------------------------------

        const User protobuf_user{
            42,
            "Protocol User",
            "protocol@example.com"
        };

        const auto encoded =
            encodeUser(protobuf_user);

        cout
            << "\n[6] Protobuf-style encoded message\n";

        cout
            << "Bytes: "
            << encoded.size()
            << "\n";

        cout
            << "Hex: "
            << bytesToHex(encoded)
            << "\n";

        // --------------------------------------------------------------------
        // Idempotent payment operation.
        // --------------------------------------------------------------------

        PaymentService payment_service;

        cout
            << "\n[7] Idempotent payment\n";

        const string key =
            "order-5001-payment";

        cout
            << "First attempt: "
            << payment_service.charge(
                2499.0,
                key
            )
            << "\n";

        cout
            << "Retry attempt: "
            << payment_service.charge(
                2499.0,
                key
            )
            << "\n";

        cout
            << "Total received: "
            << payment_service.totalReceived()
            << "\n";

        // --------------------------------------------------------------------
        // Retry demonstration.
        // --------------------------------------------------------------------

        int temporary_attempts = 0;

        const auto retry_result =
            retryWithBackoff(
                [&]() -> string {
                    ++temporary_attempts;

                    if (temporary_attempts < 3) {
                        throw TemporaryFailure(
                            "Temporary dependency failure."
                        );
                    }

                    return "retry succeeded";
                },
                4,
                10ms
            );

        cout
            << "\n[8] Retry result: "
            << retry_result
            << "\n";

        cout
            << "Attempts: "
            << temporary_attempts
            << "\n";

        // --------------------------------------------------------------------
        // Circuit breaker demonstration.
        // --------------------------------------------------------------------

        CircuitBreaker breaker(2);

        cout
            << "\n[9] Circuit breaker\n";

        for (int attempt = 1;
             attempt <= 2;
             ++attempt) {
            try {
                breaker.execute(
                    []() -> string {
                        throw TemporaryFailure(
                            "Downstream unavailable."
                        );
                    }
                );
            }
            catch (const TemporaryFailure&) {
                cout
                    << "Failure "
                    << attempt
                    << " recorded.\n";
            }
        }

        try {
            breaker.execute(
                []() -> string {
                    return "This should not execute.";
                }
            );
        }
        catch (const RpcException& error) {
            cout
                << "Fail-fast result: "
                << statusToString(error.code())
                << "\n";
        }

        // --------------------------------------------------------------------
        // Load balancing.
        // --------------------------------------------------------------------

        auto instance_one =
            make_shared<ServiceInstance>(
                ServiceInstance{"user-service-1"}
            );

        auto instance_two =
            make_shared<ServiceInstance>(
                ServiceInstance{"user-service-2"}
            );

        auto instance_three =
            make_shared<ServiceInstance>(
                ServiceInstance{"user-service-3"}
            );

        RoundRobinBalancer balancer({
            instance_one,
            instance_two,
            instance_three
        });

        cout
            << "\n[10] Round-robin load balancing\n";

        for (int index = 0;
             index < 6;
             ++index) {
            auto selected =
                balancer.choose();

            cout
                << selected->address
                << "\n";

            --selected->active_requests;
        }

        // --------------------------------------------------------------------
        // Health checking.
        // --------------------------------------------------------------------

        HealthService health;

        health.setStatus(
            "user-service",
            HealthState::SERVING
        );

        health.setStatus(
            "order-service",
            HealthState::SERVING
        );

        cout
            << "\n[11] Health checking\n";

        cout
            << "user-service: "
            << healthToString(
                health.check("user-service")
            )
            << "\n";

        cout
            << "missing-service: "
            << healthToString(
                health.check("missing-service")
            )
            << "\n";

        // --------------------------------------------------------------------
        // Bounded concurrency.
        // --------------------------------------------------------------------

        Bulkhead bulkhead(2);

        cout
            << "\n[12] Bounded concurrent work\n";

        vector<future<string>> futures;

        for (int index = 1;
             index <= 4;
             ++index) {
            futures.push_back(
                async(
                    launch::async,
                    [&bulkhead, index]() {
                        return bulkhead.execute(
                            [index]() {
                                this_thread::sleep_for(
                                    20ms
                                );

                                return
                                    string("task-")
                                    + to_string(index)
                                    + " completed";
                            }
                        );
                    }
                )
            );
        }

        for (auto& future : futures) {
            cout
                << future.get()
                << "\n";
        }

        // --------------------------------------------------------------------
        // Parallel downstream aggregation.
        // --------------------------------------------------------------------

        cout
            << "\n[13] Parallel downstream operations\n";

        auto profile_future =
            async(
                launch::async,
                []() {
                    this_thread::sleep_for(
                        20ms
                    );

                    return string(
                        "profile service complete"
                    );
                }
            );

        auto orders_future =
            async(
                launch::async,
                []() {
                    this_thread::sleep_for(
                        30ms
                    );

                    return string(
                        "order service complete"
                    );
                }
            );

        auto recommendations_future =
            async(
                launch::async,
                []() {
                    this_thread::sleep_for(
                        10ms
                    );

                    return string(
                        "recommendation service complete"
                    );
                }
            );

        cout
            << profile_future.get()
            << "\n";

        cout
            << orders_future.get()
            << "\n";

        cout
            << recommendations_future.get()
            << "\n";

        // --------------------------------------------------------------------
        // Deadline budget.
        // --------------------------------------------------------------------

        cout
            << "\n[14] Deadline budget\n";

        cout
            << "Remaining budget: "
            << remainingBudget(context).count()
            << " ms\n";

        // --------------------------------------------------------------------
        // Performance comparison.
        // --------------------------------------------------------------------

        vector<User> many_users;

        for (int index = 1;
             index <= 100000;
             ++index) {
            many_users.push_back(
                User{
                    index,
                    "user-" + to_string(index),
                    "user-" + to_string(index)
                        + "@example.com"
                }
            );
        }

        const auto indexing_started =
            chrono::steady_clock::now();

        auto user_index =
            buildUserIndex(many_users);

        const auto indexing_finished =
            chrono::steady_clock::now();

        const double indexing_ms =
            chrono::duration<double, milli>(
                indexing_finished
                - indexing_started
            ).count();

        cout
            << "\n[15] User index\n";

        cout
            << "Users indexed: "
            << user_index.size()
            << "\n";

        cout
            << "Index construction time: "
            << fixed
            << setprecision(3)
            << indexing_ms
            << " ms\n";

        /*
         * A vector search is O(n).
         *
         * An unordered_map lookup is O(1) average-case.
         *
         * The trade-off is additional memory and hash-table behavior.
         * Distributed service performance also depends heavily on network
         * latency, serialization, queueing, database latency, and contention.
         */

        const auto lookup_iterator =
            user_index.find(99999);

        if (lookup_iterator != user_index.end()) {
            cout
                << "Indexed lookup: "
                << lookup_iterator->second.name
                << "\n";
        }

        // --------------------------------------------------------------------
        // Metrics.
        // --------------------------------------------------------------------

        cout
            << "\n[16] RPC metrics\n";

        cout
            << "Calls: "
            << metrics.calls()
            << "\n";

        cout
            << "Failures: "
            << metrics.failures()
            << "\n";

        cout
            << "Average latency: "
            << fixed
            << setprecision(3)
            << metrics.averageLatencyMs()
            << " ms\n";

        // --------------------------------------------------------------------
        // Schema evolution notes.
        // --------------------------------------------------------------------

        cout
            << "\n[17] Schema evolution rules\n";

        cout
            << "- Keep existing protobuf field numbers stable.\n";

        cout
            << "- Do not reuse removed field numbers.\n";

        cout
            << "- Add new fields with new field numbers.\n";

        cout
            << "- Consider reserving removed field numbers and names.\n";

        cout
            << "- Test compatibility between deployed client/server versions.\n";

        // --------------------------------------------------------------------
        // Architecture.
        // --------------------------------------------------------------------

        cout
            << "\n[18] Architecture\n";

        cout
            << R"ARCH(
Client
  |
  | gRPC / HTTP/2
  v
Dashboard Service
  |
  +-------------------+
  |                   |
  v                   v
User Service      Order Service
  |                   |
  v                   v
User Store        Order Store

Shared operational concerns:
- deadlines
- status codes
- authentication
- authorization
- TLS
- service discovery
- load balancing
- health checking
- retries
- idempotency
- circuit breaking
- bounded concurrency
- metrics
- logs
- tracing
- resource limits
)ARCH";

        // --------------------------------------------------------------------
        // Edge-case tests.
        // --------------------------------------------------------------------

        cout
            << "\n[19] Edge-case tests\n";

        try {
            user_service.getUser(
                GetUserRequest{0},
                context
            );
        }
        catch (const RpcException& error) {
            cout
                << "Invalid ID: "
                << statusToString(error.code())
                << "\n";
        }

        try {
            stream_service.serverStreaming(-1);
        }
        catch (const RpcException& error) {
            cout
                << "Negative stream limit: "
                << statusToString(error.code())
                << "\n";
        }

        try {
            payment_service.charge(
                -10.0,
                "bad-payment"
            );
        }
        catch (const RpcException& error) {
            cout
                << "Invalid payment: "
                << statusToString(error.code())
                << "\n";
        }

        // --------------------------------------------------------------------
        // Final integrated result.
        // --------------------------------------------------------------------

        cout
            << "\n[20] Integrated request result\n";

        const auto final_dashboard =
            dashboard_service.getDashboard(
                1,
                context
            );

        cout
            << "{\n"
            << "  user_id: "
            << final_dashboard.user.id
            << ",\n"
            << "  user_name: "
            << final_dashboard.user.name
            << ",\n"
            << "  order_count: "
            << final_dashboard.orders.size()
            << ",\n"
            << "  total_value: "
            << fixed
            << setprecision(2)
            << final_dashboard.total_value
            << "\n"
            << "}\n";

        cout
            << "\nCase study completed successfully.\n";
    }
    catch (const exception& error) {
        cerr
            << "Fatal error: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
