#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

enum class MetricType {
    Counter,
    Gauge,
    Histogram
};

struct Labels {
    std::map<std::string, std::string> values;

    bool operator<(const Labels& other) const {
        return values < other.values;
    }
};

class MetricError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

class Metric {
protected:
    std::string name_;
    std::string description_;
    MetricType type_;
    std::set<std::string> label_names_;

    void validateLabels(const Labels& labels) const {
        std::set<std::string> actual;

        for (const auto& [key, value] : labels.values) {
            if (key.empty() || key.size() > 128 ||
                value.size() > 128) {
                throw MetricError("Invalid metric label.");
            }

            actual.insert(key);
        }

        if (actual != label_names_) {
            throw MetricError("Metric label mismatch.");
        }
    }

    static void validateName(const std::string& name) {
        if (name.empty() ||
            !std::isalpha(static_cast<unsigned char>(name[0])) &&
            name[0] != '_' && name[0] != ':') {
            throw MetricError("Invalid metric name.");
        }

        for (char c : name) {
            if (!std::isalnum(static_cast<unsigned char>(c)) &&
                c != '_' && c != ':') {
                throw MetricError("Invalid metric name.");
            }
        }
    }

public:
    Metric(
        std::string name,
        std::string description,
        MetricType type,
        std::set<std::string> labelNames = {}
    )
        : name_(std::move(name)),
          description_(std::move(description)),
          type_(type),
          label_names_(std::move(labelNames)) {
        validateName(name_);
    }

    virtual ~Metric() = default;

    const std::string& name() const {
        return name_;
    }

    MetricType type() const {
        return type_;
    }
};

class Counter : public Metric {
private:
    std::map<Labels, double> values_;
    mutable std::mutex mutex_;

public:
    Counter(
        std::string name,
        std::string description,
        std::set<std::string> labels = {}
    )
        : Metric(
            std::move(name),
            std::move(description),
            MetricType::Counter,
            std::move(labels)
        ) {}

    double increment(
        double amount = 1,
        const Labels& labels = {}
    ) {
        if (!std::isfinite(amount) || amount <= 0) {
            throw MetricError(
                "Counter increments must be positive."
            );
        }

        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);
        return values_[labels] += amount;
    }

    double get(const Labels& labels = {}) const {
        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto it = values_.find(labels);
        return it == values_.end() ? 0 : it->second;
    }
};

class Gauge : public Metric {
private:
    std::map<Labels, double> values_;
    mutable std::mutex mutex_;

public:
    Gauge(
        std::string name,
        std::string description,
        std::set<std::string> labels = {}
    )
        : Metric(
            std::move(name),
            std::move(description),
            MetricType::Gauge,
            std::move(labels)
        ) {}

    void set(double value, const Labels& labels = {}) {
        if (!std::isfinite(value)) {
            throw MetricError("Invalid gauge value.");
        }

        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);
        values_[labels] = value;
    }

    double add(double amount, const Labels& labels = {}) {
        if (!std::isfinite(amount)) {
            throw MetricError("Invalid gauge increment.");
        }

        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);
        return values_[labels] += amount;
    }

    double get(const Labels& labels = {}) const {
        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto it = values_.find(labels);
        return it == values_.end() ? 0 : it->second;
    }
};

class Histogram : public Metric {
private:
    struct Series {
        std::uint64_t count = 0;
        double sum = 0;
        std::vector<std::uint64_t> buckets;
        std::vector<double> samples;
    };

    std::vector<double> boundaries_;
    std::map<Labels, Series> series_;
    mutable std::mutex mutex_;

public:
    Histogram(
        std::string name,
        std::string description,
        std::vector<double> boundaries,
        std::set<std::string> labels = {}
    )
        : Metric(
            std::move(name),
            std::move(description),
            MetricType::Histogram,
            std::move(labels)
        ),
          boundaries_(std::move(boundaries)) {

        if (boundaries_.empty() ||
            !std::is_sorted(
                boundaries_.begin(),
                boundaries_.end()
            ) ||
            std::adjacent_find(
                boundaries_.begin(),
                boundaries_.end()
            ) != boundaries_.end()) {
            throw MetricError("Invalid histogram boundaries.");
        }

        for (double boundary : boundaries_) {
            if (!std::isfinite(boundary) || boundary <= 0) {
                throw MetricError("Invalid bucket boundary.");
            }
        }
    }

    void observe(
        double value,
        const Labels& labels = {}
    ) {
        if (!std::isfinite(value) || value < 0) {
            throw MetricError("Invalid histogram observation.");
        }

        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto& s = series_[labels];

        if (s.buckets.empty()) {
            s.buckets.resize(boundaries_.size(), 0);
        }

        ++s.count;
        s.sum += value;

        for (std::size_t i = 0; i < boundaries_.size(); ++i) {
            if (value <= boundaries_[i]) {
                ++s.buckets[i];
            }
        }

        // Bounded sample retention is used only for local
        // percentile estimation, not for exact long-term history.
        if (s.samples.size() < 10000) {
            s.samples.push_back(value);
        }
    }

    std::uint64_t count(const Labels& labels = {}) const {
        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto it = series_.find(labels);
        return it == series_.end() ? 0 : it->second.count;
    }

    std::optional<double> percentile(
        double quantile,
        const Labels& labels = {}
    ) const {
        if (quantile < 0 || quantile > 1) {
            throw MetricError("Invalid quantile.");
        }

        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto it = series_.find(labels);

        if (it == series_.end() ||
            it->second.samples.empty()) {
            return std::nullopt;
        }

        auto values = it->second.samples;
        std::sort(values.begin(), values.end());

        std::size_t index = std::max<std::size_t>(
            0,
            static_cast<std::size_t>(
                std::ceil(quantile * values.size())
            ) - 1
        );

        return values[index];
    }

    void report(const Labels& labels = {}) const {
        validateLabels(labels);

        std::lock_guard<std::mutex> guard(mutex_);

        auto it = series_.find(labels);

        if (it == series_.end()) {
            std::cout << "No histogram observations.\n";
            return;
        }

        const auto& s = it->second;

        std::cout << "Count: " << s.count
                  << "\nSum: " << s.sum << '\n';

        for (std::size_t i = 0; i < boundaries_.size(); ++i) {
            std::cout << "Bucket <= "
                      << boundaries_[i]
                      << ": " << s.buckets[i] << '\n';
        }

        std::cout << "Bucket +Inf: " << s.count << '\n';
    }
};

struct SLIResult {
    std::string name;
    double good;
    double total;
    std::optional<double> value;
    double target;
    std::optional<bool> passed;
};

class ServiceLevelIndicator {
private:
    std::string name_;
    double target_;

public:
    ServiceLevelIndicator(std::string name, double target)
        : name_(std::move(name)), target_(target) {
        if (target < 0 || target > 1) {
            throw MetricError("Invalid SLI target.");
        }
    }

    SLIResult evaluate(double good, double total) const {
        if (!std::isfinite(good) ||
            !std::isfinite(total) ||
            total < 0 ||
            good < 0 ||
            good > total) {
            throw MetricError("Invalid SLI data.");
        }

        if (total == 0) {
            return {
                name_, good, total, std::nullopt,
                target_, std::nullopt
            };
        }

        double value = good / total;

        return {
            name_,
            good,
            total,
            value,
            target_,
            value >= target_
        };
    }
};

class RepositoryMetrics {
private:
    Counter requests_{
        "http_requests_total",
        "Total HTTP requests",
        {"method", "status"}
    };

    Gauge active_{
        "http_active_requests",
        "Currently active HTTP requests"
    };

    Histogram latency_{
        "http_request_duration_seconds",
        "HTTP request latency",
        {0.05, 0.1, 0.25, 0.5, 1, 2, 5},
        {"method"}
    };

    ServiceLevelIndicator availability_{
        "availability", 0.999
    };

public:
    void completeRequest(
        const std::string& method,
        int status,
        double duration
    ) {
        if (status < 100 || status > 599) {
            throw MetricError("Invalid HTTP status.");
        }

        if (duration < 0 || !std::isfinite(duration)) {
            throw MetricError("Invalid duration.");
        }

        Labels requestLabels{
            {{"method", method},
             {"status", std::to_string(status)}}
        };

        Labels latencyLabels{
            {{"method", method}}
        };

        requests_.increment(1, requestLabels);
        latency_.observe(duration, latencyLabels);
    }

    void show() const {
        std::cout << "\nHTTP GET 200: "
                  << requests_.get({
                      {{"method", "GET"}, {"status", "200"}}
                  }) << '\n';

        std::cout << "Active requests: "
                  << active_.get() << '\n';

        std::cout << "Latency histogram:\n";

        latency_.report({{{"method", "GET"}}});

        auto result = availability_.evaluate(9990, 10000);

        std::cout << "\nAvailability: "
                  << std::fixed << std::setprecision(5)
                  << *result.value * 100 << "%\n";

        std::cout << "Target: "
                  << result.target * 100 << "%\n";

        std::cout << "SLI passed: "
                  << (*result.passed ? "yes" : "no")
                  << '\n';
    }
};

int main() {
    try {
        RepositoryMetrics metrics;

        metrics.completeRequest("GET", 200, 0.045);
        metrics.completeRequest("GET", 200, 0.080);
        metrics.completeRequest("GET", 200, 0.120);
        metrics.completeRequest("GET", 500, 1.400);
        metrics.completeRequest("POST", 201, 0.250);

        metrics.show();

        ServiceLevelIndicator latencySli{
            "fast_response_ratio", 0.95
        };

        auto result = latencySli.evaluate(970, 1000);

        std::cout << "\nFast response SLI: "
                  << *result.value * 100
                  << "%\n";

        std::cout << "Eligible: "
                  << (*result.passed ? "yes" : "no")
                  << '\n';

        try {
            metrics.completeRequest("GET", 200, -1);
        } catch (const MetricError& error) {
            std::cout << "\nRejected invalid observation: "
                      << error.what() << '\n';
        }

    } catch (const std::exception& error) {
        std::cerr << "Metrics system failure: "
                  << error.what() << '\n';

        return 1;
    }

    return 0;
}
