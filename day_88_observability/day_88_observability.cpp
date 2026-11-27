#include <algorithm>
#include <chrono>
#include <cstdint>
#include <ctime>
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

// ---------------------------------------------------------
// 1. Repository-independent observability domain
// ---------------------------------------------------------

enum class Severity : int {
    DEBUG = 10,
    INFO = 20,
    WARNING = 30,
    ERROR = 40,
    CRITICAL = 50
};

string severityName(Severity severity) {
    switch (severity) {
        case Severity::DEBUG: return "DEBUG";
        case Severity::INFO: return "INFO";
        case Severity::WARNING: return "WARNING";
        case Severity::ERROR: return "ERROR";
        case Severity::CRITICAL: return "CRITICAL";
    }

    throw invalid_argument("Unknown severity");
}

struct TraceContext {
    string traceId;
    string spanId;
    string correlationId;
    string requestId;
};

struct LogEvent {
    uint64_t sequence;
    string timestamp;
    Severity severity;
    string service;
    string environment;
    string eventName;
    string message;
    TraceContext context;
    map<string, string> attributes;
};

// ---------------------------------------------------------
// 2. Time and event utilities
// ---------------------------------------------------------

string currentTimestamp() {
    using namespace chrono;

    const auto now = system_clock::now();
    const time_t timestamp = system_clock::to_time_t(now);

    tm utc{};

#ifdef _WIN32
    gmtime_s(&utc, &timestamp);
#else
    gmtime_r(&timestamp, &utc);
#endif

    const auto milliseconds =
        duration_cast<milliseconds>(
            now.time_since_epoch()
        ).count() % 1000;

    ostringstream output;

    output << put_time(&utc, "%Y-%m-%dT%H:%M:%S")
           << "."
           << setw(3)
           << setfill('0')
           << milliseconds
           << "Z";

    return output.str();
}

string escapeJson(const string& value) {
    ostringstream output;

    for (unsigned char ch : value) {
        switch (ch) {
            case '"': output << "\\\""; break;
            case '\\': output << "\\\\"; break;
            case '\n': output << "\\n"; break;
            case '\r': output << "\\r"; break;
            case '\t': output << "\\t"; break;

            default:
                if (ch < 0x20) {
                    output << "\\u"
                           << hex
                           << setw(4)
                           << setfill('0')
                           << static_cast<int>(ch)
                           << dec;
                } else {
                    output << static_cast<char>(ch);
                }
        }
    }

    return output.str();
}

string randomIdentifier(uint64_t value) {
    ostringstream output;
    output << hex << setw(16) << setfill('0') << value;
    return output.str();
}

// ---------------------------------------------------------
// 3. Sensitive-data policy
// ---------------------------------------------------------

class RedactionPolicy {
private:
    const set<string> sensitiveKeys = {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "credit_card"
    };

public:
    string sanitize(
        const string& key,
        const string& value
    ) const {
        string normalized = key;

        transform(
            normalized.begin(),
            normalized.end(),
            normalized.begin(),
            [](unsigned char c) {
                return static_cast<char>(tolower(c));
            }
        );

        if (sensitiveKeys.count(normalized)) {
            return "[REDACTED]";
        }

        return value;
    }
};

// ---------------------------------------------------------
// 4. Structured JSON serialization
// ---------------------------------------------------------

class JsonSerializer {
public:
    static string serialize(const LogEvent& event) {
        ostringstream output;

        output << "{"
               << "\"sequence\":" << event.sequence << ","
               << "\"timestamp\":\""
               << escapeJson(event.timestamp) << "\","
               << "\"severity\":\""
               << severityName(event.severity) << "\","
               << "\"service\":\""
               << escapeJson(event.service) << "\","
               << "\"environment\":\""
               << escapeJson(event.environment) << "\","
               << "\"event_name\":\""
               << escapeJson(event.eventName) << "\","
               << "\"message\":\""
               << escapeJson(event.message) << "\","
               << "\"trace_id\":\""
               << escapeJson(event.context.traceId) << "\","
               << "\"span_id\":\""
               << escapeJson(event.context.spanId) << "\","
               << "\"correlation_id\":\""
               << escapeJson(event.context.correlationId) << "\","
               << "\"request_id\":\""
               << escapeJson(event.context.requestId) << "\","
               << "\"attributes\":{";

        bool first = true;

        for (const auto& [key, value] : event.attributes) {
            if (!first) {
                output << ",";
            }

            first = false;

            output << "\""
                   << escapeJson(key)
                   << "\":\""
                   << escapeJson(value)
                   << "\"";
        }

        output << "}}";

        return output.str();
    }
};

// ---------------------------------------------------------
// 5. Bounded centralized collector
// ---------------------------------------------------------

class CentralCollector {
private:
    vector<LogEvent> events;
    size_t capacity;
    uint64_t nextSequence = 1;
    size_t rejected = 0;

public:
    explicit CentralCollector(size_t maximumEvents)
        : capacity(maximumEvents) {
        if (capacity == 0) {
            throw invalid_argument("Capacity must be positive");
        }

        events.reserve(capacity);
    }

    bool ingest(LogEvent event) {
        if (
            event.service.empty() ||
            event.eventName.empty() ||
            event.context.traceId.empty()
        ) {
            rejected++;
            return false;
        }

        if (events.size() >= capacity) {
            // A bounded collector prevents unbounded memory growth.
            rejected++;
            return false;
        }

        event.sequence = nextSequence++;

        events.push_back(std::move(event));

        return true;
    }

    vector<LogEvent> query(
        const string& service = "",
        optional<Severity> minimumSeverity = nullopt,
        const string& traceId = ""
    ) const {
        vector<LogEvent> result;

        copy_if(
            events.begin(),
            events.end(),
            back_inserter(result),
            [&](const LogEvent& event) {
                const bool serviceMatches =
                    service.empty() || event.service == service;

                const bool severityMatches =
                    !minimumSeverity ||
                    static_cast<int>(event.severity) >=
                    static_cast<int>(*minimumSeverity);

                const bool traceMatches =
                    traceId.empty() ||
                    event.context.traceId == traceId;

                return serviceMatches &&
                       severityMatches &&
                       traceMatches;
            }
        );

        return result;
    }

    size_t rejectedCount() const {
        return rejected;
    }

    const vector<LogEvent>& allEvents() const {
        return events;
    }
};

// ---------------------------------------------------------
// 6. Logger and application instrumentation
// ---------------------------------------------------------

class StructuredLogger {
private:
    string service;
    string environment;
    Severity minimumLevel;
    RedactionPolicy redaction;
    CentralCollector& collector;

public:
    StructuredLogger(
        string serviceName,
        string environmentName,
        Severity minimum,
        CentralCollector& centralCollector
    )
        : service(std::move(serviceName)),
          environment(std::move(environmentName)),
          minimumLevel(minimum),
          collector(centralCollector) {
        if (service.empty() || environment.empty()) {
            throw invalid_argument(
                "Service and environment are required"
            );
        }
    }

    bool log(
        Severity severity,
        const string& eventName,
        const string& message,
        const TraceContext& context,
        map<string, string> attributes = {}
    ) {
        if (static_cast<int>(severity) <
            static_cast<int>(minimumLevel)) {
            return true;
        }

        if (eventName.empty() || context.traceId.empty()) {
            throw invalid_argument(
                "Event name and trace ID are required"
            );
        }

        map<string, string> safeAttributes;

        for (const auto& [key, value] : attributes) {
            safeAttributes[key] = redaction.sanitize(key, value);
        }

        LogEvent event{
            0,
            currentTimestamp(),
            severity,
            service,
            environment,
            eventName,
            message,
            context,
            std::move(safeAttributes)
        };

        return collector.ingest(std::move(event));
    }
};

class PaymentService {
private:
    StructuredLogger& logger;

public:
    explicit PaymentService(StructuredLogger& structuredLogger)
        : logger(structuredLogger) {}

    bool process(
        double amount,
        const TraceContext& context,
        bool simulateFailure = false
    ) {
        if (logger.log(
            Severity::INFO,
            "payment.started",
            "Payment processing started",
            context,
            {{"amount", to_string(amount)}}
        ) == false) {
            throw runtime_error("Central log collector unavailable");
        }

        try {
            if (amount <= 0) {
                throw invalid_argument(
                    "Payment amount must be positive"
                );
            }

            if (simulateFailure) {
                throw runtime_error(
                    "Payment gateway unavailable"
                );
            }

            return logger.log(
                Severity::INFO,
                "payment.completed",
                "Payment completed",
                context,
                {
                    {"amount", to_string(amount)},
                    {"status", "COMPLETED"}
                }
            );
        } catch (const exception& error) {
            const bool logged = logger.log(
                Severity::ERROR,
                "payment.failed",
                "Payment processing failed",
                context,
                {
                    {"error_type", typeid(error).name()},
                    {"error_message", error.what()}
                }
            );

            if (!logged) {
                throw runtime_error(
                    "Payment failed and error logging was rejected"
                );
            }

            throw;
        }
    }
};

// ---------------------------------------------------------
// 7. Governance and alert evaluation
// ---------------------------------------------------------

struct AlertRule {
    string name;
    string service;
    double errorThreshold;
    size_t minimumEvents;
};

class ObservabilityEngine {
private:
    const CentralCollector& collector;

public:
    explicit ObservabilityEngine(
        const CentralCollector& centralCollector
    )
        : collector(centralCollector) {}

    map<string, size_t> eventDistribution() const {
        map<string, size_t> result;

        for (const auto& event : collector.allEvents()) {
            result[event.eventName]++;
        }

        return result;
    }

    double errorRate(const string& service) const {
        const auto events = collector.query(service);

        if (events.empty()) {
            return 0.0;
        }

        const auto errors = count_if(
            events.begin(),
            events.end(),
            [](const LogEvent& event) {
                return static_cast<int>(event.severity) >=
                       static_cast<int>(Severity::ERROR);
            }
        );

        return static_cast<double>(errors) / events.size();
    }

    bool evaluate(const AlertRule& rule) const {
        if (
            rule.errorThreshold < 0 ||
            rule.errorThreshold > 1 ||
            rule.minimumEvents == 0
        ) {
            throw invalid_argument("Invalid alert rule");
        }

        const auto events = collector.query(rule.service);

        return events.size() >= rule.minimumEvents &&
               errorRate(rule.service) >= rule.errorThreshold;
    }
};

// ---------------------------------------------------------
// 8. Main execution
// ---------------------------------------------------------

int main() {
    try {
        CentralCollector collector(1000);

        StructuredLogger logger(
            "payment-service",
            "production",
            Severity::DEBUG,
            collector
        );

        PaymentService paymentService(logger);

        TraceContext context{
            "trace-2026-001",
            "span-001",
            "order-1001",
            "request-001"
        };

        cout << "OBSERVABILITY PIPELINE\n\n";

        paymentService.process(1200.50, context);

        try {
            paymentService.process(500.00, context, true);
        } catch (const runtime_error& error) {
            cout << "Expected failure: " << error.what() << "\n";
        }

        try {
            paymentService.process(0, context);
        } catch (const invalid_argument& error) {
            cout << "Expected validation error: "
                 << error.what() << "\n";
        }

        logger.log(
            Severity::WARNING,
            "authentication.failure",
            "Invalid authentication attempt",
            context,
            {
                {"username", "analyst"},
                {"password", "example-password"},
                {"access_token", "private-token"}
            }
        );

        cout << "\nCENTRALIZED JSON LOGS\n";

        for (const auto& event : collector.allEvents()) {
            cout << JsonSerializer::serialize(event) << "\n";
        }

        cout << "\nTRACE CORRELATION\n";

        const auto traceEvents = collector.query(
            "",
            nullopt,
            context.traceId
        );

        cout << "Trace: " << context.traceId << "\n";
        cout << "Related events: " << traceEvents.size() << "\n";

        cout << "\nSERVICE ERROR RATE\n";

        ObservabilityEngine engine(collector);

        const double rate = engine.errorRate("payment-service");

        cout << fixed << setprecision(2)
             << rate * 100 << "%\n";

        AlertRule rule{
            "payment-error-rate",
            "payment-service",
            0.30,
            3
        };

        cout << "\nALERT STATUS\n";

        cout << (
            engine.evaluate(rule) ? "FIRING" : "NORMAL"
        ) << "\n";

        cout << "\nEVENT DISTRIBUTION\n";

        for (const auto& [name, count] :
             engine.eventDistribution()) {
            cout << name << ": " << count << "\n";
        }

        // Verify security and trace-correlation invariants.
        const auto securityEvents = collector.query(
            "payment-service",
            Severity::WARNING
        );

        const auto securityEvent = find_if(
            securityEvents.begin(),
            securityEvents.end(),
            [](const LogEvent& event) {
                return event.eventName ==
                       "authentication.failure";
            }
        );

        if (securityEvent == securityEvents.end()) {
            throw runtime_error("Security event missing");
        }

        if (
            securityEvent->attributes.at("password") !=
            "[REDACTED]"
        ) {
            throw runtime_error("Password redaction failed");
        }

        if (
            securityEvent->attributes.at("access_token") !=
            "[REDACTED]"
        ) {
            throw runtime_error("Token redaction failed");
        }

        if (traceEvents.size() != 4) {
            throw runtime_error("Unexpected trace event count");
        }

        cout << "\nAll validation checks passed.\n";

        cout << "Rejected events: "
             << collector.rejectedCount() << "\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << "\n";
        return 1;
    }

    return 0;
}
