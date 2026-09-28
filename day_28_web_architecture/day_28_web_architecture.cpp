/*
Web Architecture: Synchronous vs Asynchronous Communication
Blocking, Non-Blocking, and Asynchronous Workflows

C++17 industry-style case study:
An order-processing gateway demonstrates how a web backend can combine
validation, synchronous CPU work, asynchronous-style scheduling, queues,
worker threads, timeouts, retries, idempotency, circuit breaking,
dependency management, and observability.

Build:
    g++ -std=c++17 -O2 -pthread main.cpp -o web_workflow

Run:
    ./web_workflow
*/

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <future>
#include <iomanip>
#include <iostream>
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
#include <unordered_set>
#include <utility>
#include <vector>

using namespace std::chrono_literals;


// ---------------------------------------------------------------------------
// 1. COMMON UTILITIES
// ---------------------------------------------------------------------------

class Logger {
private:
    std::mutex mutex_;

public:
    void info(const std::string& message) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::cout << "[INFO] " << message << '\n';
    }

    void error(const std::string& message) {
        std::lock_guard<std::mutex> lock(mutex_);
        std::cerr << "[ERROR] " << message << '\n';
    }
};

Logger logger;

std::string currentThreadId() {
    std::ostringstream output;
    output << std::this_thread::get_id();
    return output.str();
}


// ---------------------------------------------------------------------------
// 2. BASIC SYNCHRONOUS OPERATION
// ---------------------------------------------------------------------------

std::string synchronousServiceCall(
    const std::string& service,
    std::chrono::milliseconds delay
) {
    logger.info(
        "Synchronous call started: " + service +
        " on thread " + currentThreadId()
    );

    std::this_thread::sleep_for(delay);

    logger.info("Synchronous call completed: " + service);
    return service + ": success";
}

void demonstrateSynchronousCommunication() {
    logger.info("=== 1. Synchronous communication ===");

    auto start = std::chrono::steady_clock::now();

    auto first = synchronousServiceCall("inventory", 40ms);
    auto second = synchronousServiceCall("fraud-check", 40ms);

    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start
    );

    logger.info(first);
    logger.info(second);
    logger.info("Sequential elapsed time: " + std::to_string(elapsed.count()) + "ms");
}


// ---------------------------------------------------------------------------
// 3. NON-BLOCKING SUBMISSION WITH std::async
// ---------------------------------------------------------------------------

void demonstrateAsyncSubmission() {
    logger.info("=== 2. Non-blocking submission ===");

    auto start = std::chrono::steady_clock::now();

    auto inventory = std::async(
        std::launch::async,
        synchronousServiceCall,
        "inventory",
        40ms
    );

    auto fraud = std::async(
        std::launch::async,
        synchronousServiceCall,
        "fraud-check",
        40ms
    );

    logger.info("Both operations have been submitted.");
    logger.info("The caller can perform other local work.");

    volatile std::uint64_t localCalculation = 0;
    for (std::uint64_t i = 0; i < 100000; ++i) {
        localCalculation += i;
    }

    auto inventoryResult = inventory.get();
    auto fraudResult = fraud.get();

    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - start
    );

    logger.info(inventoryResult);
    logger.info(fraudResult);
    logger.info(
        "Concurrent waiting elapsed time: " +
        std::to_string(elapsed.count()) + "ms"
    );
}


// ---------------------------------------------------------------------------
// 4. ORDER DOMAIN MODEL
// ---------------------------------------------------------------------------

struct Order {
    std::string orderId;
    std::string customerId;
    double amount{};
};

struct ServiceResult {
    bool success{};
    std::string service;
    std::string message;
    int attempts{};
    long long durationMilliseconds{};
};

void validateOrder(const Order& order) {
    if (order.orderId.empty()) {
        throw std::invalid_argument("orderId is required");
    }

    if (order.customerId.empty()) {
        throw std::invalid_argument("customerId is required");
    }

    if (!(order.amount > 0.0)) {
        throw std::invalid_argument("amount must be greater than zero");
    }

    if (order.amount > 1'000'000.0) {
        throw std::invalid_argument("amount exceeds transaction limit");
    }
}


// ---------------------------------------------------------------------------
// 5. THREAD-SAFE BOUNDED QUEUE
// ---------------------------------------------------------------------------

template <typename T>
class BoundedQueue {
private:
    std::queue<T> items_;
    std::size_t capacity_;

    std::mutex mutex_;
    std::condition_variable notEmpty_;
    std::condition_variable notFull_;
    bool stopped_ = false;

public:
    explicit BoundedQueue(std::size_t capacity)
        : capacity_(capacity) {
        if (capacity == 0) {
            throw std::invalid_argument("Queue capacity must be positive");
        }
    }

    bool push(T item) {
        std::unique_lock<std::mutex> lock(mutex_);

        /*
         * Waiting here is intentional backpressure:
         * a producer cannot create unlimited pending work.
         */
        notFull_.wait(lock, [this] {
            return items_.size() < capacity_ || stopped_;
        });

        if (stopped_) {
            return false;
        }

        items_.push(std::move(item));
        notEmpty_.notify_one();
        return true;
    }

    std::optional<T> pop() {
        std::unique_lock<std::mutex> lock(mutex_);

        notEmpty_.wait(lock, [this] {
            return !items_.empty() || stopped_;
        });

        if (items_.empty()) {
            return std::nullopt;
        }

        T item = std::move(items_.front());
        items_.pop();

        notFull_.notify_one();
        return item;
    }

    void stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopped_ = true;
        }

        notEmpty_.notify_all();
        notFull_.notify_all();
    }
};


// ---------------------------------------------------------------------------
// 6. WORKER POOL
// ---------------------------------------------------------------------------

class WorkerPool {
private:
    BoundedQueue<std::function<void()>> jobs_;
    std::vector<std::thread> workers_;

public:
    WorkerPool(std::size_t workerCount, std::size_t queueCapacity)
        : jobs_(queueCapacity) {

        if (workerCount == 0) {
            throw std::invalid_argument("Worker count must be positive");
        }

        for (std::size_t i = 0; i < workerCount; ++i) {
            workers_.emplace_back([this, i] {
                logger.info(
                    "Worker " + std::to_string(i) + " started."
                );

                while (true) {
                    auto job = jobs_.pop();

                    if (!job.has_value()) {
                        break;
                    }

                    try {
                        (*job)();
                    } catch (const std::exception& error) {
                        logger.error(
                            "Worker exception: " +
                            std::string(error.what())
                        );
                    }
                }

                logger.info(
                    "Worker " + std::to_string(i) + " stopped."
                );
            });
        }
    }

    ~WorkerPool() {
        jobs_.stop();

        for (auto& worker : workers_) {
            if (worker.joinable()) {
                worker.join();
            }
        }
    }

    bool submit(std::function<void()> job) {
        return jobs_.push(std::move(job));
    }
};


// ---------------------------------------------------------------------------
// 7. IDEMPOTENCY STORE
// ---------------------------------------------------------------------------

class IdempotencyStore {
private:
    std::unordered_map<std::string, ServiceResult> results_;
    std::mutex mutex_;

public:
    std::optional<ServiceResult> find(const std::string& key) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto iterator = results_.find(key);

        if (iterator == results_.end()) {
            return std::nullopt;
        }

        return iterator->second;
    }

    void store(const std::string& key, const ServiceResult& result) {
        std::lock_guard<std::mutex> lock(mutex_);
        results_[key] = result;
    }
};


// ---------------------------------------------------------------------------
// 8. CIRCUIT BREAKER
// ---------------------------------------------------------------------------

class CircuitBreaker {
public:
    enum class State {
        Closed,
        Open,
        HalfOpen
    };

private:
    State state_ = State::Closed;
    int failures_ = 0;
    int failureThreshold_;
    std::chrono::milliseconds recoveryTime_;
    std::chrono::steady_clock::time_point openedAt_;
    std::mutex mutex_;

public:
    CircuitBreaker(
        int failureThreshold,
        std::chrono::milliseconds recoveryTime
    )
        : failureThreshold_(failureThreshold),
          recoveryTime_(recoveryTime) {}

    bool allowRequest() {
        std::lock_guard<std::mutex> lock(mutex_);

        if (state_ == State::Closed) {
            return true;
        }

        if (
            state_ == State::Open &&
            std::chrono::steady_clock::now() - openedAt_ >= recoveryTime_
        ) {
            state_ = State::HalfOpen;
            return true;
        }

        return state_ == State::HalfOpen;
    }

    void recordSuccess() {
        std::lock_guard<std::mutex> lock(mutex_);
        failures_ = 0;
        state_ = State::Closed;
    }

    void recordFailure() {
        std::lock_guard<std::mutex> lock(mutex_);

        ++failures_;

        if (failures_ >= failureThreshold_) {
            state_ = State::Open;
            openedAt_ = std::chrono::steady_clock::now();
        }
    }

    std::string stateName() const {
        switch (state_) {
            case State::Closed:
                return "CLOSED";
            case State::Open:
                return "OPEN";
            case State::HalfOpen:
                return "HALF_OPEN";
        }

        return "UNKNOWN";
    }
};


// ---------------------------------------------------------------------------
// 9. REMOTE SERVICE SIMULATION
// ---------------------------------------------------------------------------

class RemoteService {
private:
    std::string name_;
    int failuresBeforeSuccess_;
    std::atomic<int> calls_{0};

public:
    RemoteService(
        std::string name,
        int failuresBeforeSuccess
    )
        : name_(std::move(name)),
          failuresBeforeSuccess_(failuresBeforeSuccess) {}

    ServiceResult call(
        const std::string& operation,
        std::chrono::milliseconds latency
    ) {
        const auto start = std::chrono::steady_clock::now();

        std::this_thread::sleep_for(latency);

        const int callNumber = ++calls_;

        if (callNumber <= failuresBeforeSuccess_) {
            auto elapsed =
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - start
                );

            return {
                false,
                name_,
                operation + ": transient failure",
                callNumber,
                elapsed.count()
            };
        }

        auto elapsed =
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start
            );

        return {
            true,
            name_,
            operation + ": success",
            callNumber,
            elapsed.count()
        };
    }
};


// ---------------------------------------------------------------------------
// 10. RETRY POLICY
// ---------------------------------------------------------------------------

class RetryPolicy {
private:
    int maxAttempts_;
    std::chrono::milliseconds baseDelay_;

public:
    RetryPolicy(
        int maxAttempts,
        std::chrono::milliseconds baseDelay
    )
        : maxAttempts_(maxAttempts),
          baseDelay_(baseDelay) {}

    template <typename Function>
    ServiceResult execute(Function function) const {
        ServiceResult result;

        for (int attempt = 1; attempt <= maxAttempts_; ++attempt) {
            result = function();
            result.attempts = attempt;

            if (result.success) {
                return result;
            }

            if (attempt < maxAttempts_) {
                /*
                 * Exponential backoff limits immediate repeated pressure
                 * against a failing dependency.
                 */
                const auto delay =
                    baseDelay_ * (1LL << (attempt - 1));

                std::this_thread::sleep_for(delay);
            }
        }

        return result;
    }
};


// ---------------------------------------------------------------------------
// 11. ORDER PROCESSOR
// ---------------------------------------------------------------------------

class OrderProcessor {
private:
    RemoteService inventoryService_{"inventory", 1};
    RemoteService fraudService_{"fraud", 0};
    RemoteService paymentService_{"payment", 0};

    RetryPolicy retryPolicy_{3, 10ms};
    CircuitBreaker paymentBreaker_{2, 100ms};
    IdempotencyStore idempotencyStore_;

public:
    ServiceResult reserveInventory(const Order& order) {
        return retryPolicy_.execute([&] {
            return inventoryService_.call(
                "reserve " + order.orderId,
                25ms
            );
        });
    }

    ServiceResult runFraudCheck(const Order& order) {
        return retryPolicy_.execute([&] {
            return fraudService_.call(
                "screen " + order.orderId,
                20ms
            );
        });
    }

    ServiceResult authorizePayment(const Order& order) {
        if (!paymentBreaker_.allowRequest()) {
            return {
                false,
                "payment",
                "circuit breaker is OPEN",
                0,
                0
            };
        }

        auto result = retryPolicy_.execute([&] {
            return paymentService_.call(
                "authorize " + order.orderId,
                25ms
            );
        });

        if (result.success) {
            paymentBreaker_.recordSuccess();
        } else {
            paymentBreaker_.recordFailure();
        }

        return result;
    }

    ServiceResult process(
        const Order& order,
        const std::string& idempotencyKey
    ) {
        validateOrder(order);

        /*
         * Idempotency must be checked before performing an irreversible
         * state-changing operation. A production implementation would also
         * atomically reserve the key to prevent concurrent duplicate requests.
         */
        if (auto previous = idempotencyStore_.find(idempotencyKey)) {
            logger.info("Returning idempotent result for " + idempotencyKey);
            return *previous;
        }

        /*
         * Inventory and fraud screening are independent after validation,
         * so they can execute concurrently.
         */
        auto inventoryFuture = std::async(
            std::launch::async,
            &OrderProcessor::reserveInventory,
            this,
            std::cref(order)
        );

        auto fraudFuture = std::async(
            std::launch::async,
            &OrderProcessor::runFraudCheck,
            this,
            std::cref(order)
        );

        auto inventory = inventoryFuture.get();
        auto fraud = fraudFuture.get();

        if (!inventory.success) {
            throw std::runtime_error(
                "Inventory processing failed: " + inventory.message
            );
        }

        if (!fraud.success) {
            throw std::runtime_error(
                "Fraud screening failed: " + fraud.message
            );
        }

        /*
         * Payment has a dependency on successful inventory and fraud results,
         * so it begins only after those prerequisites are satisfied.
         */
        auto payment = authorizePayment(order);

        if (!payment.success) {
            throw std::runtime_error(
                "Payment processing failed: " + payment.message
            );
        }

        ServiceResult finalResult{
            true,
            "order-gateway",
            "Order " + order.orderId + " accepted",
            payment.attempts,
            inventory.durationMilliseconds +
                fraud.durationMilliseconds +
                payment.durationMilliseconds
        };

        idempotencyStore_.store(idempotencyKey, finalResult);

        return finalResult;
    }
};


// ---------------------------------------------------------------------------
// 12. ASYNCHRONOUS JOB ACCEPTANCE
// ---------------------------------------------------------------------------

struct Job {
    std::string id;
    std::atomic<int> progress{0};
    std::atomic<bool> completed{false};
    std::string result;
    std::mutex mutex;
};

class JobManager {
private:
    std::unordered_map<std::string, std::shared_ptr<Job>> jobs_;
    std::mutex mutex_;

public:
    std::shared_ptr<Job> submit(WorkerPool& pool) {
        static std::atomic<unsigned long> counter{0};

        auto job = std::make_shared<Job>();
        job->id = "JOB-" + std::to_string(++counter);

        {
            std::lock_guard<std::mutex> lock(mutex_);
            jobs_[job->id] = job;
        }

        const bool accepted = pool.submit([job] {
            for (int progress = 0; progress <= 100; progress += 20) {
                std::this_thread::sleep_for(20ms);
                job->progress = progress;
            }

            {
                std::lock_guard<std::mutex> lock(job->mutex);
                job->result = "Long-running report completed";
            }

            job->completed = true;
        });

        if (!accepted) {
            throw std::runtime_error("Job queue rejected work");
        }

        return job;
    }

    std::shared_ptr<Job> get(const std::string& id) {
        std::lock_guard<std::mutex> lock(mutex_);

        auto iterator = jobs_.find(id);

        if (iterator == jobs_.end()) {
            throw std::out_of_range("Unknown job ID");
        }

        return iterator->second;
    }
};


// ---------------------------------------------------------------------------
// 13. TEST CASES
// ---------------------------------------------------------------------------

void testValidation() {
    logger.info("=== 3. Validation tests ===");

    Order valid{"ORD-1", "CUS-1", 500.0};
    validateOrder(valid);
    logger.info("Valid order accepted.");

    const std::vector<Order> invalidOrders{
        {"", "CUS-1", 100.0},
        {"ORD-2", "", 100.0},
        {"ORD-3", "CUS-3", 0.0},
        {"ORD-4", "CUS-4", 2'000'000.0}
    };

    for (const auto& order : invalidOrders) {
        try {
            validateOrder(order);
            logger.error("Invalid order unexpectedly accepted.");
        } catch (const std::exception& error) {
            logger.info(
                "Invalid order correctly rejected: " +
                std::string(error.what())
            );
        }
    }
}


void testIdempotency(OrderProcessor& processor) {
    logger.info("=== 4. Idempotency test ===");

    Order order{"ORD-IDEMPOTENT", "CUS-7", 750.0};

    auto first = processor.process(order, "IDEMPOTENCY-001");
    auto second = processor.process(order, "IDEMPOTENCY-001");

    logger.info("First:  " + first.message);
    logger.info("Second: " + second.message);
    logger.info(
        "Both calls returned the stored result without repeating the "
        "completed logical operation."
    );
}


void demonstrateLongRunningJob() {
    logger.info("=== 5. Long-running asynchronous job ===");

    WorkerPool pool(2, 4);
    JobManager manager;

    auto job = manager.submit(pool);

    logger.info("Job accepted immediately: " + job->id);

    while (!job->completed.load()) {
        logger.info(
            "Job " + job->id +
            " progress=" +
            std::to_string(job->progress.load()) +
            "%"
        );

        std::this_thread::sleep_for(15ms);
    }

    {
        std::lock_guard<std::mutex> lock(job->mutex);
        logger.info("Job result: " + job->result);
    }
}


// ---------------------------------------------------------------------------
// 14. EVENT-DRIVEN PROCESSING CASE
// ---------------------------------------------------------------------------

struct DomainEvent {
    std::string eventType;
    std::string eventId;
    std::string orderId;
};

class EventDispatcher {
private:
    using Handler = std::function<void(const DomainEvent&)>;

    std::unordered_map<std::string, std::vector<Handler>> handlers_;
    std::mutex mutex_;

public:
    void subscribe(
        const std::string& eventType,
        Handler handler
    ) {
        std::lock_guard<std::mutex> lock(mutex_);
        handlers_[eventType].push_back(std::move(handler));
    }

    void publish(const DomainEvent& event) {
        std::vector<Handler> selectedHandlers;

        {
            std::lock_guard<std::mutex> lock(mutex_);

            auto iterator = handlers_.find(event.eventType);

            if (iterator != handlers_.end()) {
                selectedHandlers = iterator->second;
            }
        }

        /*
         * Copying handlers before execution prevents holding the dispatcher
         * mutex while arbitrary application code executes.
         */
        for (const auto& handler : selectedHandlers) {
            std::thread(handler, event).detach();
        }
    }
};


void demonstrateEventDrivenCommunication() {
    logger.info("=== 6. Event-driven communication ===");

    EventDispatcher dispatcher;

    dispatcher.subscribe(
        "order.created",
        [](const DomainEvent& event) {
            std::this_thread::sleep_for(15ms);
            logger.info(
                "Audit consumer processed " + event.eventId
            );
        }
    );

    dispatcher.subscribe(
        "order.created",
        [](const DomainEvent& event) {
            std::this_thread::sleep_for(20ms);
            logger.info(
                "Notification consumer processed " + event.eventId
            );
        }
    );

    dispatcher.publish({
        "order.created",
        "EVT-1001",
        "ORD-1001"
    });

    /*
     * Detached threads are used only for this compact demonstration.
     * Production systems need managed worker lifetimes and graceful shutdown.
     */
    std::this_thread::sleep_for(30ms);
}


// ---------------------------------------------------------------------------
// 15. TIMEOUT DEMONSTRATION
// ---------------------------------------------------------------------------

void demonstrateTimeout() {
    logger.info("=== 7. Future timeout ===");

    auto future = std::async(
        std::launch::async,
        [] {
            std::this_thread::sleep_for(100ms);
            return std::string("slow operation completed");
        }
    );

    if (
        future.wait_for(20ms) ==
        std::future_status::ready
    ) {
        logger.info(future.get());
    } else {
        /*
         * A timed wait only stops the caller from waiting immediately.
         * It does not automatically terminate the worker computation.
         */
        logger.info(
            "Timeout reached. The operation is still executing."
        );

        logger.info("Later result: " + future.get());
    }
}


// ---------------------------------------------------------------------------
// 16. COMPLEXITY AND ARCHITECTURAL NOTES
// ---------------------------------------------------------------------------

void printArchitectureNotes() {
    logger.info("=== 8. Architectural considerations ===");

    const std::vector<std::string> notes{
        "Independent I/O operations can overlap.",
        "Dependent operations must respect their dependency order.",
        "Bounded queues provide backpressure.",
        "Retries should target transient failures rather than every error.",
        "Exponential backoff reduces immediate retry pressure.",
        "Idempotency protects state-changing operations from duplicate retries.",
        "Timeouts prevent indefinite waiting.",
        "Circuit breakers can fail fast when a dependency repeatedly fails.",
        "Thread pools limit concurrent execution resources.",
        "Observability should measure latency, status, errors, and queue pressure.",
        "CPU-bound work and I/O-bound work have different concurrency characteristics.",
        "Graceful shutdown must stop accepting new work and drain or cancel existing work."
    };

    for (std::size_t index = 0; index < notes.size(); ++index) {
        logger.info(
            std::to_string(index + 1) + ". " + notes[index]
        );
    }
}


// ---------------------------------------------------------------------------
// 17. MAIN CASE STUDY
// ---------------------------------------------------------------------------

int main() {
    try {
        demonstrateSynchronousCommunication();
        demonstrateAsyncSubmission();

        testValidation();

        OrderProcessor processor;

        logger.info("=== 9. Complete order-processing case study ===");

        Order order{
            "ORD-9001",
            "CUS-9001",
            4999.0
        };

        auto result = processor.process(
            order,
            "PAYMENT-REQUEST-9001"
        );

        logger.info(
            "Order result: " + result.message
        );

        logger.info(
            "Total recorded downstream duration: " +
            std::to_string(result.durationMilliseconds) +
            "ms"
        );

        testIdempotency(processor);
        demonstrateLongRunningJob();
        demonstrateEventDrivenCommunication();
        demonstrateTimeout();
        printArchitectureNotes();

        logger.info("=== Case study completed successfully ===");
        return 0;
    } catch (const std::exception& error) {
        logger.error(
            "Fatal application error: " +
            std::string(error.what())
        );
        return 1;
    }
}
