#include <algorithm>
#include <chrono>
#include <functional>
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

enum class ServiceStatus {
    Registered,
    Healthy,
    Deploying,
    Degraded,
    Unavailable
};

enum class DeploymentStatus {
    Pending,
    Successful,
    Failed,
    RolledBack
};

string toString(ServiceStatus status) {
    switch (status) {
        case ServiceStatus::Registered: return "REGISTERED";
        case ServiceStatus::Healthy: return "HEALTHY";
        case ServiceStatus::Deploying: return "DEPLOYING";
        case ServiceStatus::Degraded: return "DEGRADED";
        case ServiceStatus::Unavailable: return "UNAVAILABLE";
    }
    return "UNKNOWN";
}

string toString(DeploymentStatus status) {
    switch (status) {
        case DeploymentStatus::Pending: return "PENDING";
        case DeploymentStatus::Successful: return "SUCCESSFUL";
        case DeploymentStatus::Failed: return "FAILED";
        case DeploymentStatus::RolledBack: return "ROLLED_BACK";
    }
    return "UNKNOWN";
}

struct Version {
    int major;
    int minor;
    int patch;

    static Version parse(const string& value) {
        Version version{};
        char dot1, dot2;
        stringstream input(value);

        if (!(input >> version.major >> dot1
                    >> version.minor >> dot2
                    >> version.patch) ||
            dot1 != '.' || dot2 != '.' ||
            version.major < 0 ||
            version.minor < 0 ||
            version.patch < 0) {
            throw invalid_argument("Invalid semantic version: " + value);
        }

        string extra;
        if (input >> extra) {
            throw invalid_argument("Invalid version suffix.");
        }

        return version;
    }

    string str() const {
        return to_string(major) + "." +
               to_string(minor) + "." +
               to_string(patch);
    }

    bool operator<(const Version& other) const {
        return tie(major, minor, patch) <
               tie(other.major, other.minor, other.patch);
    }
};

struct Contract {
    Version version;
    int apiVersion;
    set<string> endpoints;
    bool backwardCompatible;
};

struct Service {
    string name;
    string description;
    Contract contract;
    set<string> dependencies;
    ServiceStatus status = ServiceStatus::Registered;
    int instances = 1;
    int deploymentCount = 0;
};

struct Deployment {
    int id;
    string serviceName;
    Version previousVersion;
    Version targetVersion;
    DeploymentStatus status;
    string message;
};

class ServiceRegistry {
private:
    map<string, Service> services;

    void visit(
        const string& name,
        set<string>& visited,
        set<string>& active,
        vector<string>& result
    ) const {
        if (active.count(name)) {
            throw runtime_error(
                "Circular dependency detected: " + name
            );
        }

        if (visited.count(name)) return;

        auto it = services.find(name);

        if (it == services.end()) {
            throw runtime_error("Unknown service: " + name);
        }

        active.insert(name);

        for (const auto& dependency : it->second.dependencies) {
            visit(dependency, visited, active, result);
        }

        active.erase(name);
        visited.insert(name);
        result.push_back(name);
    }

public:
    void registerService(Service service) {
        if (service.name.empty() || service.description.empty()) {
            throw invalid_argument("Service metadata is required.");
        }

        if (service.instances < 1) {
            throw invalid_argument("Instance count must be positive.");
        }

        if (service.contract.apiVersion < 1 ||
            service.contract.endpoints.empty()) {
            throw invalid_argument("Invalid service contract.");
        }

        if (services.count(service.name)) {
            throw runtime_error("Duplicate service registration.");
        }

        services.emplace(service.name, move(service));
    }

    Service& get(const string& name) {
        auto it = services.find(name);

        if (it == services.end()) {
            throw runtime_error("Service not found: " + name);
        }

        return it->second;
    }

    const Service& get(const string& name) const {
        auto it = services.find(name);

        if (it == services.end()) {
            throw runtime_error("Service not found: " + name);
        }

        return it->second;
    }

    vector<string> deploymentOrder() const {
        set<string> visited;
        set<string> active;
        vector<string> result;

        for (const auto& [name, service] : services) {
            visit(name, visited, active, result);
        }

        return result;
    }

    vector<string> consumers(const string& provider) const {
        get(provider);

        vector<string> result;

        for (const auto& [name, service] : services) {
            if (service.dependencies.count(provider)) {
                result.push_back(name);
            }
        }

        return result;
    }

    void validateDependencies(const string& name) const {
        get(name);

        // The graph traversal also detects missing dependencies and cycles.
        deploymentOrder();
    }

    void display() const {
        cout << left
             << setw(24) << "SERVICE"
             << setw(15) << "VERSION"
             << setw(16) << "STATUS"
             << setw(12) << "INSTANCES"
             << "DEPENDENCIES\n";

        for (const auto& [name, service] : services) {
            cout << left
                 << setw(24) << name
                 << setw(15) << service.contract.version.str()
                 << setw(16) << toString(service.status)
                 << setw(12) << service.instances;

            for (const auto& dependency : service.dependencies) {
                cout << dependency << " ";
            }

            cout << '\n';
        }
    }
};

class ContractValidator {
public:
    static void validate(
        const Contract& oldContract,
        const Contract& newContract
    ) {
        if (newContract.apiVersion < oldContract.apiVersion) {
            throw runtime_error("API version downgrade rejected.");
        }

        vector<string> removed;

        set_difference(
            oldContract.endpoints.begin(),
            oldContract.endpoints.end(),
            newContract.endpoints.begin(),
            newContract.endpoints.end(),
            back_inserter(removed)
        );

        if (!removed.empty() &&
            newContract.apiVersion <= oldContract.apiVersion) {
            throw runtime_error(
                "Breaking endpoint removal requires a new API version."
            );
        }

        if (!removed.empty() && newContract.backwardCompatible) {
            throw runtime_error(
                "Breaking contract marked as backward compatible."
            );
        }
    }
};

class DeploymentEngine {
private:
    ServiceRegistry& registry;
    vector<Deployment> history;
    int nextId = 1;

public:
    explicit DeploymentEngine(ServiceRegistry& registry)
        : registry(registry) {}

    Deployment deploy(
        const string& name,
        const Contract& target,
        bool healthCheck
    ) {
        Service& service = registry.get(name);

        registry.validateDependencies(name);

        ContractValidator::validate(service.contract, target);

        Version previous = service.contract.version;

        Deployment record{
            nextId++,
            name,
            previous,
            target.version,
            DeploymentStatus::Pending,
            ""
        };

        service.status = ServiceStatus::Deploying;

        try {
            if (!healthCheck) {
                throw runtime_error(
                    "Post-deployment health check failed."
                );
            }

            service.contract = target;
            service.status = ServiceStatus::Healthy;
            service.deploymentCount++;

            record.status = DeploymentStatus::Successful;
            record.message = "Deployment completed.";

        } catch (const exception& error) {
            // The old contract remains active after a failed deployment.
            service.status = ServiceStatus::Healthy;

            record.status = DeploymentStatus::RolledBack;
            record.message = error.what();
        }

        history.push_back(record);
        return record;
    }

    Deployment rollback(
        const string& name,
        const Version& target
    ) {
        Service& service = registry.get(name);

        auto it = find_if(
            history.rbegin(),
            history.rend(),
            [&](const Deployment& deployment) {
                return deployment.serviceName == name &&
                       deployment.targetVersion.str() == target.str() &&
                       deployment.status ==
                           DeploymentStatus::Successful;
            }
        );

        if (it == history.rend()) {
            throw runtime_error("No successful rollback target.");
        }

        // This demonstration stores the previous version in deployment
        // history. A production engine would retain the complete artifact
        // and configuration, not just the version number.
        auto previous = find_if(
            history.rbegin(),
            history.rend(),
            [&](const Deployment& deployment) {
                return deployment.serviceName == name &&
                       deployment.targetVersion.str() ==
                           it->previousVersion.str() &&
                       deployment.status ==
                           DeploymentStatus::Successful;
            }
        );

        if (previous == history.rend()) {
            throw runtime_error(
                "Previous deployment artifact is unavailable."
            );
        }

        throw runtime_error(
            "Version metadata exists, but artifact restoration "
            "requires a deployment artifact store."
        );
    }

    const vector<Deployment>& getHistory() const {
        return history;
    }
};

struct Event {
    string id;
    string type;
    string source;
    string payload;
};

class EventBroker {
private:
    using Handler = function<void(const Event&)>;

    map<string, vector<pair<string, Handler>>> subscribers;
    set<string> processed;
    vector<Event> deadLetters;

public:
    void subscribe(
        const string& eventType,
        const string& consumer,
        Handler handler
    ) {
        if (consumer.empty() || !handler) {
            throw invalid_argument("Invalid subscription.");
        }

        auto& handlers = subscribers[eventType];

        auto duplicate = find_if(
            handlers.begin(),
            handlers.end(),
            [&](const auto& item) {
                return item.first == consumer;
            }
        );

        if (duplicate != handlers.end()) {
            throw runtime_error("Duplicate event subscription.");
        }

        handlers.emplace_back(consumer, move(handler));
    }

    void publish(const Event& event) {
        if (event.id.empty() || event.type.empty()) {
            throw invalid_argument("Invalid event.");
        }

        if (processed.count(event.id)) {
            cout << "Duplicate event ignored: "
                 << event.id << '\n';
            return;
        }

        auto it = subscribers.find(event.type);

        if (it == subscribers.end()) {
            processed.insert(event.id);
            return;
        }

        bool failed = false;

        for (const auto& [consumer, handler] : it->second) {
            try {
                handler(event);
            } catch (const exception& error) {
                failed = true;

                cerr << "Consumer " << consumer
                     << " failed: " << error.what() << '\n';
            }
        }

        if (failed) {
            deadLetters.push_back(event);
        }

        processed.insert(event.id);
    }

    size_t deadLetterCount() const {
        return deadLetters.size();
    }
};

Service makeService(
    string name,
    string description,
    int instances,
    set<string> dependencies,
    Version version
) {
    Service service;

    service.name = move(name);
    service.description = move(description);
    service.instances = instances;
    service.dependencies = move(dependencies);

    service.contract = Contract{
        version,
        1,
        {"/health", "/api"},
        true
    };

    return service;
}

int main() {
    try {
        cout << "MICROSERVICES GOVERNANCE ENGINE\n";
        cout << string(55, '=') << "\n\n";

        ServiceRegistry registry;

        registry.registerService(
            makeService(
                "payment-service",
                "Payment processing",
                3,
                {},
                Version::parse("1.0.0")
            )
        );

        registry.registerService(
            makeService(
                "inventory-service",
                "Stock management",
                2,
                {},
                Version::parse("1.0.0")
            )
        );

        registry.registerService(
            makeService(
                "order-service",
                "Order management",
                3,
                {"payment-service", "inventory-service"},
                Version::parse("1.0.0")
            )
        );

        cout << "SERVICE INVENTORY\n";
        registry.display();

        cout << "\nDEPENDENCY ORDER\n";

        for (const auto& name : registry.deploymentOrder()) {
            cout << name << '\n';
        }

        cout << "\nINDEPENDENT DEPLOYMENT\n";

        DeploymentEngine engine(registry);

        Contract updatedPayment{
            Version::parse("1.1.0"),
            1,
            {"/health", "/api", "/api/status"},
            true
        };

        Deployment success = engine.deploy(
            "payment-service",
            updatedPayment,
            true
        );

        cout << success.serviceName
             << " -> " << toString(success.status)
             << " -> " << success.targetVersion.str()
             << '\n';

        cout << "\nFAILED DEPLOYMENT\n";

        Contract updatedInventory{
            Version::parse("1.1.0"),
            1,
            {"/health", "/api", "/api/availability"},
            true
        };

        Deployment failure = engine.deploy(
            "inventory-service",
            updatedInventory,
            false
        );

        cout << failure.serviceName
             << " -> " << toString(failure.status)
             << " -> " << failure.message
             << '\n';

        cout << "\nCONTRACT VALIDATION\n";

        try {
            Contract breaking{
                Version::parse("2.0.0"),
                1,
                {"/health"},
                true
            };

            ContractValidator::validate(
                registry.get("payment-service").contract,
                breaking
            );

        } catch (const exception& error) {
            cout << "Rejected: " << error.what() << '\n';
        }

        cout << "\nEVENT-DRIVEN COMMUNICATION\n";

        EventBroker broker;
        vector<string> receivedOrders;

        broker.subscribe(
            "order.created",
            "inventory-consumer",
            [&](const Event& event) {
                receivedOrders.push_back(event.payload);

                cout << "Inventory received: "
                     << event.payload << '\n';
            }
        );

        broker.subscribe(
            "order.created",
            "notification-consumer",
            [&](const Event& event) {
                cout << "Notification received: "
                     << event.payload << '\n';
            }
        );

        Event orderEvent{
            "EVENT-1001",
            "order.created",
            "order-service",
            "ORD-3001"
        };

        broker.publish(orderEvent);
        broker.publish(orderEvent);

        if (receivedOrders.size() != 1) {
            throw runtime_error("Event idempotency test failed.");
        }

        cout << "\nSERVICE CONSUMERS\n";

        for (const auto& consumer :
             registry.consumers("payment-service")) {
            cout << consumer << '\n';
        }

        cout << "\nFINAL INVENTORY\n";
        registry.display();

        cout << "\nDEPLOYMENT HISTORY\n";

        for (const auto& deployment : engine.getHistory()) {
            cout << deployment.serviceName
                 << " | " << deployment.targetVersion.str()
                 << " | " << toString(deployment.status)
                 << " | " << deployment.message << '\n';
        }

        cout << "\nDead-letter events: "
             << broker.deadLetterCount() << '\n';

        cout << "\nExecution completed.\n";

    } catch (const exception& error) {
        cerr << "Fatal error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
