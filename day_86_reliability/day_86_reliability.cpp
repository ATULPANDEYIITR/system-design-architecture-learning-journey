#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

enum class ComponentState {
    Healthy,
    Degraded,
    Failed,
    Recovering
};

enum class CircuitState {
    Closed,
    Open,
    HalfOpen
};

enum class DependencyType {
    Required,
    Optional
};

enum class CheckState {
    Passed,
    Failed,
    Pending
};

enum class MergeMode {
    Full,
    ReadOnly,
    Degraded
};

string toString(ComponentState state) {
    switch (state) {
        case ComponentState::Healthy: return "HEALTHY";
        case ComponentState::Degraded: return "DEGRADED";
        case ComponentState::Failed: return "FAILED";
        case ComponentState::Recovering: return "RECOVERING";
    }
    return "UNKNOWN";
}

string toString(CircuitState state) {
    switch (state) {
        case CircuitState::Closed: return "CLOSED";
        case CircuitState::Open: return "OPEN";
        case CircuitState::HalfOpen: return "HALF_OPEN";
    }
    return "UNKNOWN";
}

struct Dependency {
    string name;
    DependencyType type;
    ComponentState state = ComponentState::Healthy;
    CircuitState circuit = CircuitState::Closed;
    int failures = 0;
    int failureThreshold = 3;
    int recoveries = 0;
    string lastError;
    chrono::steady_clock::time_point openedAt;
    int recoveryTimeoutMs = 1000;
};

struct StatusCheck {
    string name;
    CheckState state;
    string description;
};

struct Review {
    string reviewer;
    bool eligible;
    bool dismissed;
    bool stale;
    bool approved;
};

struct BranchProtection {
    bool protectedBranch = true;
    bool requirePullRequest = true;
    bool requireLinearHistory = true;
    bool allowForcePush = false;
    bool allowDeletion = false;
    bool requireResolvedConversations = true;
    bool administratorBypass = false;
    int requiredApprovals = 2;
    set<string> requiredChecks;
};

struct PullRequest {
    int id;
    string sourceBranch;
    string targetBranch;
    string headCommit;
    string baseCommit;
    bool open = true;
    bool draft = false;
    bool conflicts = false;
    bool conversationsResolved = true;
    bool linearHistory = true;
    vector<Review> reviews;
    vector<StatusCheck> checks;
};

struct MergeDecision {
    bool eligible = false;
    MergeMode mode = MergeMode::ReadOnly;
    vector<string> blockers;
    vector<string> warnings;
};

class Repository {
private:
    map<string, Dependency> dependencies;
    BranchProtection protection;

public:
    void registerDependency(
        const string& name,
        DependencyType type,
        int threshold = 3,
        int recoveryTimeoutMs = 1000
    ) {
        if (name.empty() || threshold < 1 || recoveryTimeoutMs <= 0) {
            throw invalid_argument("Invalid dependency configuration");
        }

        if (dependencies.count(name)) {
            throw invalid_argument("Duplicate dependency");
        }

        dependencies.emplace(name, Dependency{
            name,
            type,
            ComponentState::Healthy,
            CircuitState::Closed,
            0,
            threshold,
            0,
            "",
            chrono::steady_clock::now(),
            recoveryTimeoutMs
        });
    }

    void recordFailure(const string& name, const string& reason) {
        auto it = dependencies.find(name);

        if (it == dependencies.end()) {
            throw out_of_range("Unknown dependency");
        }

        Dependency& dependency = it->second;
        dependency.failures++;
        dependency.lastError = reason;
        dependency.state = ComponentState::Degraded;

        if (
            dependency.circuit == CircuitState::HalfOpen ||
            dependency.failures >= dependency.failureThreshold
        ) {
            dependency.circuit = CircuitState::Open;
            dependency.state = ComponentState::Failed;
            dependency.openedAt = chrono::steady_clock::now();
        }
    }

    bool allowRequest(const string& name) {
        auto it = dependencies.find(name);

        if (it == dependencies.end()) {
            throw out_of_range("Unknown dependency");
        }

        Dependency& dependency = it->second;

        if (dependency.circuit == CircuitState::Closed) {
            return true;
        }

        if (dependency.circuit == CircuitState::Open) {
            auto elapsed = chrono::duration_cast<chrono::milliseconds>(
                chrono::steady_clock::now() - dependency.openedAt
            ).count();

            if (elapsed >= dependency.recoveryTimeoutMs) {
                dependency.circuit = CircuitState::HalfOpen;
                dependency.state = ComponentState::Recovering;
                return true;
            }

            return false;
        }

        return true;
    }

    void recordSuccess(const string& name) {
        auto it = dependencies.find(name);

        if (it == dependencies.end()) {
            throw out_of_range("Unknown dependency");
        }

        Dependency& dependency = it->second;
        dependency.failures = 0;
        dependency.recoveries++;
        dependency.state = ComponentState::Healthy;
        dependency.circuit = CircuitState::Closed;
        dependency.lastError.clear();
    }

    string systemState() const {
        bool degraded = false;

        for (const auto& [name, dependency] : dependencies) {
            if (
                dependency.type == DependencyType::Required &&
                dependency.state == ComponentState::Failed
            ) {
                return "UNAVAILABLE";
            }

            if (dependency.state != ComponentState::Healthy) {
                degraded = true;
            }
        }

        return degraded ? "DEGRADED" : "HEALTHY";
    }

    void configureProtection(const BranchProtection& policy) {
        if (policy.requiredApprovals < 0) {
            throw invalid_argument("Approval count cannot be negative");
        }

        protection = policy;
    }

    int countValidApprovals(const PullRequest& pr) const {
        set<string> reviewers;

        for (const Review& review : pr.reviews) {
            if (
                review.eligible &&
                !review.dismissed &&
                !review.stale &&
                review.approved
            ) {
                reviewers.insert(review.reviewer);
            }
        }

        return static_cast<int>(reviewers.size());
    }

    MergeDecision evaluate(const PullRequest& pr) const {
        MergeDecision decision;

        decision.mode = MergeMode::ReadOnly;

        if (!pr.open) {
            decision.blockers.push_back("Pull Request is closed");
        }

        if (pr.draft) {
            decision.blockers.push_back("Draft Pull Request cannot be merged");
        }

        if (pr.sourceBranch.empty() || pr.targetBranch.empty()) {
            decision.blockers.push_back("Missing branch information");
        }

        if (pr.sourceBranch == pr.targetBranch) {
            decision.blockers.push_back("Source and target branches must differ");
        }

        if (pr.conflicts) {
            decision.blockers.push_back("Merge conflicts must be resolved");
        }

        if (protection.protectedBranch) {
            if (!pr.open) {
                decision.blockers.push_back("Protected branch requires an open PR");
            }

            if (!protection.requirePullRequest) {
                decision.warnings.push_back(
                    "Pull Request requirement is disabled"
                );
            }

            if (
                protection.requireLinearHistory &&
                !pr.linearHistory
            ) {
                decision.blockers.push_back("Linear history is required");
            }

            if (
                protection.requireResolvedConversations &&
                !pr.conversationsResolved
            ) {
                decision.blockers.push_back(
                    "Unresolved review conversations remain"
                );
            }

            int approvals = countValidApprovals(pr);

            if (approvals < protection.requiredApprovals) {
                decision.blockers.push_back(
                    "Insufficient approvals: " +
                    to_string(approvals) + "/" +
                    to_string(protection.requiredApprovals)
                );
            }

            for (const string& required : protection.requiredChecks) {
                auto it = find_if(
                    pr.checks.begin(),
                    pr.checks.end(),
                    [&](const StatusCheck& check) {
                        return check.name == required;
                    }
                );

                if (it == pr.checks.end()) {
                    decision.blockers.push_back(
                        "Missing required check: " + required
                    );
                } else if (it->state != CheckState::Passed) {
                    decision.blockers.push_back(
                        "Required check not passed: " + required
                    );
                }
            }
        }

        decision.eligible = decision.blockers.empty();

        if (decision.eligible) {
            decision.mode = MergeMode::Full;
        }

        return decision;
    }

    void printHealth() const {
        cout << "\nDEPENDENCY HEALTH\n";

        for (const auto& [name, dependency] : dependencies) {
            cout << left << setw(20) << name
                 << " state=" << setw(12) << toString(dependency.state)
                 << " circuit=" << toString(dependency.circuit)
                 << " failures=" << dependency.failures
                 << " recoveries=" << dependency.recoveries
                 << '\n';
        }

        cout << "SYSTEM STATE: " << systemState() << '\n';
    }
};

void printDecision(const MergeDecision& decision) {
    cout << "\nMERGE ELIGIBILITY: "
         << (decision.eligible ? "ELIGIBLE" : "BLOCKED")
         << '\n';

    for (const string& blocker : decision.blockers) {
        cout << "BLOCKER: " << blocker << '\n';
    }

    for (const string& warning : decision.warnings) {
        cout << "WARNING: " << warning << '\n';
    }
}

int main() {
    try {
        Repository repository;

        // Register independently failing application dependencies.
        repository.registerDependency(
            "primary_database",
            DependencyType::Required
        );

        repository.registerDependency(
            "recommendation_engine",
            DependencyType::Optional
        );

        repository.registerDependency(
            "analytics",
            DependencyType::Optional
        );

        repository.recordSuccess("primary_database");

        repository.recordFailure(
            "recommendation_engine",
            "Recommendation cluster unavailable"
        );

        repository.recordFailure(
            "analytics",
            "Analytics ingestion timeout"
        );

        repository.printHealth();

        BranchProtection protection;
        protection.requiredApprovals = 2;
        protection.requiredChecks = {
            "build",
            "unit-tests",
            "security-scan"
        };

        repository.configureProtection(protection);

        PullRequest pr;
        pr.id = 104;
        pr.sourceBranch = "feature/payment-retry";
        pr.targetBranch = "main";
        pr.headCommit = "a8f12d7";
        pr.baseCommit = "c3109ab";
        pr.open = true;
        pr.draft = false;
        pr.conflicts = false;
        pr.conversationsResolved = true;
        pr.linearHistory = true;

        pr.reviews = {
            {"reviewer-1", true, false, false, true},
            {"reviewer-2", true, false, false, true},
            {"external-user", false, false, false, true},
            {"reviewer-3", true, true, false, true},
            {"reviewer-4", true, false, true, true}
        };

        pr.checks = {
            {"build", CheckState::Passed, "Build completed"},
            {"unit-tests", CheckState::Passed, "Tests passed"},
            {"security-scan", CheckState::Passed, "No blocking findings"}
        };

        cout << "\nSCENARIO 1: Healthy required dependencies, "
             << "failed optional dependencies\n";

        MergeDecision first = repository.evaluate(pr);
        printDecision(first);

        if (!first.eligible) {
            throw runtime_error("Valid PR unexpectedly blocked");
        }

        // A pending check blocks merge even with sufficient approvals.
        pr.checks[2].state = CheckState::Pending;

        cout << "\nSCENARIO 2: Security check pending\n";

        MergeDecision second = repository.evaluate(pr);
        printDecision(second);

        if (second.eligible) {
            throw runtime_error("Pending security check was accepted");
        }

        // Restore the check and introduce a merge conflict.
        pr.checks[2].state = CheckState::Passed;
        pr.conflicts = true;

        cout << "\nSCENARIO 3: Merge conflict\n";

        MergeDecision third = repository.evaluate(pr);
        printDecision(third);

        if (third.eligible) {
            throw runtime_error("Conflicted PR was accepted");
        }

        // Required dependency failure makes the service unavailable.
        repository.recordFailure(
            "primary_database",
            "Primary database connection lost"
        );
        repository.recordFailure(
            "primary_database",
            "Connection retry exhausted"
        );

        repository.printHealth();

        cout << "\nAll governance and resilience assertions passed.\n";

    } catch (const exception& error) {
        cerr << "ERROR: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
