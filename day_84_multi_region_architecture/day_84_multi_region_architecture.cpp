#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

using namespace std;

/*
 * Multi-Region Governance and Failover Engine.
 *
 * C++17 implementation of:
 * - Regional availability
 * - Active-passive architecture
 * - Replication consistency
 * - Failover policy evaluation
 * - Regional capacity management
 * - RPO and RTO evaluation
 * - Leader epochs
 * - Controlled failback
 */

enum class RegionState {
    HEALTHY,
    DEGRADED,
    UNAVAILABLE,
    RECOVERING
};

enum class RegionRole {
    PRIMARY,
    STANDBY,
    DISABLED
};

enum class Decision {
    APPROVED,
    REJECTED
};


string toString(RegionState state) {
    switch (state) {
        case RegionState::HEALTHY:
            return "HEALTHY";
        case RegionState::DEGRADED:
            return "DEGRADED";
        case RegionState::UNAVAILABLE:
            return "UNAVAILABLE";
        case RegionState::RECOVERING:
            return "RECOVERING";
    }

    throw logic_error("Unknown region state.");
}


string toString(RegionRole role) {
    switch (role) {
        case RegionRole::PRIMARY:
            return "PRIMARY";
        case RegionRole::STANDBY:
            return "STANDBY";
        case RegionRole::DISABLED:
            return "DISABLED";
    }

    throw logic_error("Unknown region role.");
}


struct Region {
    string id;
    string geography;

    RegionState state = RegionState::HEALTHY;
    RegionRole role = RegionRole::STANDBY;

    double latencyMs = 30.0;
    double replicationLagSeconds = 0.0;

    int capacity = 1000;
    int activeConnections = 0;

    long long dataVersion = 0;

    double freeCapacityRatio() const {
        if (capacity <= 0) {
            return 0.0;
        }

        return static_cast<double>(
            capacity - activeConnections
        ) / capacity;
    }
};


struct FailoverPolicy {
    double maximumReplicationLag = 5.0;
    double maximumLatencyMs = 250.0;
    double minimumFreeCapacity = 0.20;

    bool requireHealthyTarget = true;
    bool requireStandbyRole = true;
};


struct Evaluation {
    Decision decision;
    string reason;
};


struct FailoverRecord {
    string source;
    string target;

    Decision decision;
    string reason;

    double rpoSeconds;
    double estimatedRtoSeconds;

    long long leaderEpoch;
};


class Repository {

private:
    map<string, Region> regions;

    optional<string> primaryRegion;

    FailoverPolicy policy;

    vector<FailoverRecord> history;

    long long leaderEpoch = 1;

    bool failoverInProgress = false;

public:

    explicit Repository(FailoverPolicy configuration)
        : policy(configuration) {

        if (policy.maximumReplicationLag < 0 ||
            policy.maximumLatencyMs <= 0 ||
            policy.minimumFreeCapacity < 0 ||
            policy.minimumFreeCapacity >= 1) {

            throw invalid_argument("Invalid failover policy.");
        }
    }

    void addRegion(const Region& region) {

        if (region.id.empty() || region.geography.empty()) {
            throw invalid_argument(
                "Region identity and geography are required."
            );
        }

        if (region.capacity <= 0 ||
            region.activeConnections < 0 ||
            region.activeConnections > region.capacity) {

            throw invalid_argument("Invalid regional capacity.");
        }

        if (region.replicationLagSeconds < 0 ||
            region.latencyMs < 0) {

            throw invalid_argument("Invalid regional metrics.");
        }

        if (regions.count(region.id)) {
            throw invalid_argument("Duplicate region ID.");
        }

        if (region.role == RegionRole::PRIMARY) {
            if (primaryRegion.has_value()) {
                throw logic_error(
                    "Multiple primary regions are not permitted."
                );
            }

            primaryRegion = region.id;
        }

        regions.emplace(region.id, region);
    }

    Region& getRegion(const string& id) {

        auto iterator = regions.find(id);

        if (iterator == regions.end()) {
            throw out_of_range("Unknown region: " + id);
        }

        return iterator->second;
    }

    const Region& getRegion(const string& id) const {

        auto iterator = regions.find(id);

        if (iterator == regions.end()) {
            throw out_of_range("Unknown region: " + id);
        }

        return iterator->second;
    }

    Evaluation evaluate(const Region& region) const {

        if (policy.requireHealthyTarget &&
            region.state != RegionState::HEALTHY) {

            return {
                Decision::REJECTED,
                "Target is not healthy."
            };
        }

        if (region.state == RegionState::UNAVAILABLE ||
            region.state == RegionState::RECOVERING) {

            return {
                Decision::REJECTED,
                "Target cannot accept production traffic."
            };
        }

        if (policy.requireStandbyRole &&
            region.role != RegionRole::STANDBY) {

            return {
                Decision::REJECTED,
                "Target is not a standby region."
            };
        }

        if (region.replicationLagSeconds >
            policy.maximumReplicationLag) {

            return {
                Decision::REJECTED,
                "Replication lag exceeds RPO."
            };
        }

        if (region.latencyMs > policy.maximumLatencyMs) {

            return {
                Decision::REJECTED,
                "Regional latency exceeds policy."
            };
        }

        if (region.freeCapacityRatio() <
            policy.minimumFreeCapacity) {

            return {
                Decision::REJECTED,
                "Insufficient regional capacity."
            };
        }

        return {
            Decision::APPROVED,
            "All failover conditions satisfied."
        };
    }

    vector<string> eligibleRegions() const {

        vector<pair<double, string>> candidates;

        for (const auto& entry : regions) {

            const Region& region = entry.second;

            if (primaryRegion.has_value() &&
                region.id == primaryRegion.value()) {
                continue;
            }

            Evaluation result = evaluate(region);

            if (result.decision == Decision::APPROVED) {

                double score =
                    region.replicationLagSeconds * 1000.0 +
                    region.latencyMs;

                candidates.emplace_back(score, region.id);
            }
        }

        sort(candidates.begin(), candidates.end());

        vector<string> result;

        for (const auto& candidate : candidates) {
            result.push_back(candidate.second);
        }

        return result;
    }

    FailoverRecord failover(const string& targetId) {

        if (failoverInProgress) {
            throw logic_error("Failover already in progress.");
        }

        if (!primaryRegion.has_value()) {
            throw logic_error("No primary region configured.");
        }

        if (targetId == primaryRegion.value()) {
            throw invalid_argument(
                "Target must differ from current primary."
            );
        }

        Region& target = getRegion(targetId);
        Region& source = getRegion(primaryRegion.value());

        Evaluation evaluation = evaluate(target);

        if (evaluation.decision == Decision::REJECTED) {

            FailoverRecord record {
                source.id,
                target.id,
                Decision::REJECTED,
                evaluation.reason,
                target.replicationLagSeconds,
                0.0,
                leaderEpoch
            };

            history.push_back(record);

            return record;
        }

        failoverInProgress = true;

        try {

            // The epoch represents the simulated fencing generation.
            const long long nextEpoch = leaderEpoch + 1;

            if (nextEpoch <= leaderEpoch) {
                throw overflow_error("Leader epoch exhausted.");
            }

            source.role = RegionRole::STANDBY;
            target.role = RegionRole::PRIMARY;

            primaryRegion = target.id;
            leaderEpoch = nextEpoch;

            FailoverRecord record {
                source.id,
                target.id,
                Decision::APPROVED,
                "Regional promotion completed.",
                target.replicationLagSeconds,
                2.0,
                leaderEpoch
            };

            history.push_back(record);

            failoverInProgress = false;

            return record;

        } catch (...) {
            failoverInProgress = false;
            throw;
        }
    }

    void updateHealth(
        const string& id,
        RegionState state,
        double latency,
        double replicationLag
    ) {

        if (latency < 0 || replicationLag < 0) {
            throw invalid_argument("Invalid health metrics.");
        }

        Region& region = getRegion(id);

        region.state = state;
        region.latencyMs = latency;
        region.replicationLagSeconds = replicationLag;
    }

    void processWrite(const string& regionId) {

        if (!primaryRegion.has_value() ||
            primaryRegion.value() != regionId) {

            throw logic_error(
                "Writes must target the current primary."
            );
        }

        Region& region = getRegion(regionId);

        if (region.state != RegionState::HEALTHY) {
            throw runtime_error("Primary region unavailable.");
        }

        if (region.activeConnections >= region.capacity) {
            throw runtime_error("Regional capacity exhausted.");
        }

        region.activeConnections++;
        region.dataVersion++;
    }

    void replicate() {

        if (!primaryRegion.has_value()) {
            throw logic_error("No primary region.");
        }

        const Region& primary =
            getRegion(primaryRegion.value());

        for (auto& entry : regions) {

            Region& standby = entry.second;

            if (standby.id == primary.id) {
                continue;
            }

            if (standby.state == RegionState::HEALTHY) {

                standby.dataVersion = primary.dataVersion;
                standby.replicationLagSeconds = 0.0;
            }
        }
    }

    void recover(const string& id) {

        Region& region = getRegion(id);

        if (!primaryRegion.has_value()) {
            throw logic_error("No active primary.");
        }

        const Region& primary =
            getRegion(primaryRegion.value());

        region.state = RegionState::RECOVERING;

        // Synchronize the recovered replica before accepting traffic.
        region.dataVersion = primary.dataVersion;
        region.replicationLagSeconds = 0.0;
        region.activeConnections = 0;

        region.state = RegionState::HEALTHY;
        region.role = RegionRole::STANDBY;
    }

    void failback(const string& id) {

        if (!primaryRegion.has_value()) {
            throw logic_error("No active primary.");
        }

        const Region& target = getRegion(id);
        const Region& primary =
            getRegion(primaryRegion.value());

        if (target.dataVersion != primary.dataVersion) {
            throw logic_error(
                "Failback requires identical data versions."
            );
        }

        FailoverRecord record = failover(id);

        if (record.decision == Decision::REJECTED) {
            throw runtime_error(record.reason);
        }
    }

    void printReport() const {

        cout << "\nMULTI-REGION STATUS\n";

        cout << "Primary: "
             << primaryRegion.value_or("NONE")
             << "\n";

        cout << "Leader epoch: "
             << leaderEpoch
             << "\n\n";

        cout << left
             << setw(15) << "REGION"
             << setw(16) << "STATE"
             << setw(12) << "ROLE"
             << setw(12) << "LAG"
             << setw(12) << "VERSION"
             << "\n";

        for (const auto& entry : regions) {

            const Region& region = entry.second;

            cout << left
                 << setw(15) << region.id
                 << setw(16) << toString(region.state)
                 << setw(12) << toString(region.role)
                 << setw(12) << region.replicationLagSeconds
                 << setw(12) << region.dataVersion
                 << "\n";
        }

        cout << "\nFAILOVER HISTORY\n";

        for (const auto& record : history) {

            cout << record.source
                 << " -> "
                 << record.target
                 << " | "
                 << (
                     record.decision == Decision::APPROVED
                         ? "APPROVED"
                         : "REJECTED"
                 )
                 << " | "
                 << record.reason
                 << "\n";
        }
    }
};


int main() {

    try {

        FailoverPolicy policy;

        policy.maximumReplicationLag = 5.0;
        policy.maximumLatencyMs = 250.0;
        policy.minimumFreeCapacity = 0.20;

        Repository repository(policy);

        repository.addRegion({
            "ap-south-1",
            "Mumbai",
            RegionState::HEALTHY,
            RegionRole::PRIMARY,
            30.0,
            0.0,
            1000,
            100,
            0
        });

        repository.addRegion({
            "ap-south-2",
            "Hyderabad",
            RegionState::HEALTHY,
            RegionRole::STANDBY,
            45.0,
            1.0,
            1200,
            100,
            0
        });

        repository.addRegion({
            "eu-west-1",
            "Ireland",
            RegionState::HEALTHY,
            RegionRole::STANDBY,
            130.0,
            2.0,
            1500,
            100,
            0
        });

        cout << "INITIAL REGIONAL DEPLOYMENT\n";

        repository.printReport();

        cout << "\nPROCESSING WRITES\n";

        repository.processWrite("ap-south-1");
        repository.processWrite("ap-south-1");

        repository.replicate();

        cout << "\nSIMULATING PRIMARY OUTAGE\n";

        repository.updateHealth(
            "ap-south-1",
            RegionState::UNAVAILABLE,
            1000.0,
            10.0
        );

        vector<string> candidates =
            repository.eligibleRegions();

        if (candidates.empty()) {
            throw runtime_error(
                "No eligible regional failover destination."
            );
        }

        cout << "Eligible destinations:\n";

        for (const string& id : candidates) {
            cout << " - " << id << "\n";
        }

        FailoverRecord event =
            repository.failover(candidates.front());

        cout << "\nFAILOVER RESULT: "
             << event.reason
             << "\n";

        repository.processWrite(
            candidates.front()
        );

        repository.printReport();

        cout << "\nRECOVERY AND FAILBACK\n";

        repository.recover("ap-south-1");

        repository.replicate();

        repository.failback("ap-south-1");

        repository.printReport();

        cout << "\nALL GOVERNANCE VALIDATIONS PASSED\n";

    } catch (const exception& error) {

        cerr << "ERROR: " << error.what() << "\n";

        return 1;
    }

    return 0;
}
