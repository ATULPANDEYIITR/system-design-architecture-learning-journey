#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Clock = std::chrono::system_clock;
using TimePoint = Clock::time_point;
using Minutes = std::chrono::minutes;

enum class BackupType {
    FULL,
    INCREMENTAL,
    DIFFERENTIAL
};

enum class BackupState {
    CREATED,
    VERIFIED,
    FAILED,
    RESTORED
};

enum class IncidentState {
    OPEN,
    RECOVERING,
    RECOVERED,
    FAILED
};

enum class Severity {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL
};

std::string toString(BackupType type) {
    switch (type) {
        case BackupType::FULL: return "FULL";
        case BackupType::INCREMENTAL: return "INCREMENTAL";
        case BackupType::DIFFERENTIAL: return "DIFFERENTIAL";
    }

    throw std::logic_error("Unknown backup type");
}

std::string toString(BackupState state) {
    switch (state) {
        case BackupState::CREATED: return "CREATED";
        case BackupState::VERIFIED: return "VERIFIED";
        case BackupState::FAILED: return "FAILED";
        case BackupState::RESTORED: return "RESTORED";
    }

    throw std::logic_error("Unknown backup state");
}

struct RecoveryPolicy {
    std::string name;
    int rpoMinutes;
    int rtoMinutes;
    int retentionDays;
    bool requireOffsite;
    int minimumApprovals;

    void validate() const {
        if (rpoMinutes < 0 || rtoMinutes <= 0 ||
            retentionDays <= 0 || minimumApprovals < 1) {
            throw std::invalid_argument(
                "Invalid disaster recovery policy"
            );
        }
    }
};

struct Backup {
    std::string id;
    std::string system;
    BackupType type;
    TimePoint createdAt;
    std::map<std::string, long long> data;
    std::string digest;
    BackupState state;
    bool offsite;
    std::optional<std::string> parentId;
};

struct Incident {
    std::string id;
    std::string system;
    Severity severity;
    TimePoint occurredAt;
    IncidentState state;
};

struct RecoveryDecision {
    bool eligible = false;
    std::vector<std::string> violations;
    std::optional<std::string> selectedBackup;
    double actualRpoMinutes = 0;
};

struct RecoveryResult {
    std::string incidentId;
    std::string backupId;
    double actualRpoMinutes;
    double actualRtoMinutes;
    bool rpoMet;
    bool rtoMet;
    bool successful;
};

struct ProtectedSystem {
    std::string name;
    std::map<std::string, long long> data;
    RecoveryPolicy policy;
    TimePoint modifiedAt;
};

class DisasterRecoveryEngine {
private:
    std::map<std::string, ProtectedSystem> systems;
    std::map<std::string, Backup> backups;
    std::map<std::string, Incident> incidents;
    std::vector<RecoveryResult> results;

    unsigned long long nextId = 1;

    std::string generateId(const std::string& prefix) {
        return prefix + "-" + std::to_string(nextId++);
    }

    ProtectedSystem& getSystem(const std::string& name) {
        auto it = systems.find(name);

        if (it == systems.end()) {
            throw std::runtime_error("Protected system not found");
        }

        return it->second;
    }

    Backup& getBackup(const std::string& id) {
        auto it = backups.find(id);

        if (it == backups.end()) {
            throw std::runtime_error("Backup not found");
        }

        return it->second;
    }

    Incident& getIncident(const std::string& id) {
        auto it = incidents.find(id);

        if (it == incidents.end()) {
            throw std::runtime_error("Incident not found");
        }

        return it->second;
    }

    static std::string calculateDigest(
        const std::map<std::string, long long>& data
    ) {
        /*
         * Deterministic demonstration fingerprint.
         * Production systems must use a cryptographic digest such as
         * SHA-256 or an authenticated encryption construction.
         */
        unsigned long long hash = 14695981039346656037ULL;

        for (const auto& [key, value] : data) {
            const std::string item =
                key + "=" + std::to_string(value) + ";";

            for (unsigned char character : item) {
                hash ^= character;
                hash *= 1099511628211ULL;
            }
        }

        std::ostringstream output;
        output << std::hex << hash;

        return output.str();
    }

    std::optional<std::reference_wrapper<Backup>>
    latestVerifiedBackup(const std::string& systemName) {
        Backup* selected = nullptr;

        for (auto& [id, backup] : backups) {
            if (
                backup.system == systemName &&
                backup.state == BackupState::VERIFIED
            ) {
                if (
                    selected == nullptr ||
                    backup.createdAt > selected->createdAt
                ) {
                    selected = &backup;
                }
            }
        }

        if (selected == nullptr) {
            return std::nullopt;
        }

        return std::ref(*selected);
    }

public:
    void registerSystem(
        const std::string& name,
        const std::map<std::string, long long>& data,
        const RecoveryPolicy& policy
    ) {
        policy.validate();

        if (name.empty() || systems.count(name)) {
            throw std::invalid_argument(
                "Invalid or duplicate system"
            );
        }

        systems.emplace(
            name,
            ProtectedSystem{
                name,
                data,
                policy,
                Clock::now()
            }
        );
    }

    void updateSystem(
        const std::string& name,
        const std::map<std::string, long long>& changes
    ) {
        auto& system = getSystem(name);

        for (const auto& [key, value] : changes) {
            if (key.empty()) {
                throw std::invalid_argument(
                    "Data keys cannot be empty"
                );
            }

            system.data[key] = value;
        }

        system.modifiedAt = Clock::now();
    }

    std::string createBackup(
        const std::string& systemName,
        BackupType type,
        bool offsite = true
    ) {
        auto& system = getSystem(systemName);

        if (system.policy.requireOffsite && !offsite) {
            throw std::runtime_error(
                "Offsite backup requirement violated"
            );
        }

        std::optional<std::string> parent;

        if (type == BackupType::INCREMENTAL) {
            auto latest = latestVerifiedBackup(systemName);

            if (!latest.has_value()) {
                throw std::runtime_error(
                    "Incremental backup requires a verified parent"
                );
            }

            parent = latest->get().id;
        }

        Backup backup;

        backup.id = generateId("BKP");
        backup.system = systemName;
        backup.type = type;
        backup.createdAt = Clock::now();
        backup.data = system.data;
        backup.digest = calculateDigest(backup.data);
        backup.state = BackupState::CREATED;
        backup.offsite = offsite;
        backup.parentId = parent;

        const std::string id = backup.id;

        backups.emplace(id, std::move(backup));

        verifyBackup(id);

        return id;
    }

    bool verifyBackup(const std::string& id) {
        auto& backup = getBackup(id);

        if (backup.digest != calculateDigest(backup.data)) {
            backup.state = BackupState::FAILED;

            throw std::runtime_error(
                "Backup integrity verification failed"
            );
        }

        backup.state = BackupState::VERIFIED;

        return true;
    }

    std::string createIncident(
        const std::string& systemName,
        Severity severity,
        TimePoint occurredAt
    ) {
        getSystem(systemName);

        const std::string id = generateId("INC");

        incidents.emplace(
            id,
            Incident{
                id,
                systemName,
                severity,
                occurredAt,
                IncidentState::OPEN
            }
        );

        return id;
    }

    RecoveryDecision evaluateEligibility(
        const std::string& incidentId,
        int approvals,
        const std::optional<std::string>& requestedBackup =
            std::nullopt
    ) {
        const auto& incident = getIncident(incidentId);
        const auto& system = getSystem(incident.system);

        RecoveryDecision decision;

        if (incident.state != IncidentState::OPEN) {
            decision.violations.push_back(
                "Incident is not open"
            );
        }

        if (approvals < system.policy.minimumApprovals) {
            decision.violations.push_back(
                "Insufficient independent recovery approvals"
            );
        }

        const Backup* selected = nullptr;

        for (const auto& [id, backup] : backups) {
            if (backup.system != incident.system) {
                continue;
            }

            if (
                requestedBackup.has_value() &&
                id != requestedBackup.value()
            ) {
                continue;
            }

            if (backup.state != BackupState::VERIFIED) {
                continue;
            }

            if (backup.createdAt > incident.occurredAt) {
                continue;
            }

            if (
                system.policy.requireOffsite &&
                !backup.offsite
            ) {
                continue;
            }

            if (
                selected == nullptr ||
                backup.createdAt > selected->createdAt
            ) {
                selected = &backup;
            }
        }

        if (selected == nullptr) {
            decision.violations.push_back(
                "No eligible verified backup exists"
            );
        } else {
            decision.selectedBackup = selected->id;

            decision.actualRpoMinutes =
                std::chrono::duration<double, std::ratio<60>>(
                    incident.occurredAt - selected->createdAt
                ).count();

            if (
                decision.actualRpoMinutes >
                system.policy.rpoMinutes
            ) {
                decision.violations.push_back(
                    "RPO target cannot be met by selected backup"
                );
            }
        }

        decision.eligible = decision.violations.empty();

        return decision;
    }

    RecoveryResult restore(
        const std::string& incidentId,
        int approvals,
        const std::optional<std::string>& requestedBackup =
            std::nullopt
    ) {
        auto& incident = getIncident(incidentId);
        auto& system = getSystem(incident.system);

        const auto decision = evaluateEligibility(
            incidentId,
            approvals,
            requestedBackup
        );

        if (!decision.eligible) {
            std::ostringstream message;

            for (const auto& violation : decision.violations) {
                message << violation << "; ";
            }

            throw std::runtime_error(message.str());
        }

        incident.state = IncidentState::RECOVERING;

        const auto started = Clock::now();

        try {
            auto& backup = getBackup(
                decision.selectedBackup.value()
            );

            verifyBackup(backup.id);

            // Stage the complete snapshot before replacing active data.
            auto stagedData = backup.data;

            if (stagedData.empty()) {
                throw std::runtime_error(
                    "Restored snapshot cannot be empty"
                );
            }

            system.data.swap(stagedData);
            system.modifiedAt = backup.createdAt;

            backup.state = BackupState::RESTORED;
            incident.state = IncidentState::RECOVERED;

            const auto completed = Clock::now();

            const double actualRto =
                std::chrono::duration<double, std::ratio<60>>(
                    completed - started
                ).count();

            RecoveryResult result{
                incidentId,
                backup.id,
                decision.actualRpoMinutes,
                actualRto,
                decision.actualRpoMinutes <=
                    system.policy.rpoMinutes,
                actualRto <= system.policy.rtoMinutes,
                true
            };

            results.push_back(result);

            return result;

        } catch (...) {
            incident.state = IncidentState::FAILED;
            throw;
        }
    }

    void displaySystem(const std::string& name) {
        const auto& system = getSystem(name);

        std::cout << "\nSystem: " << system.name << "\n";

        for (const auto& [key, value] : system.data) {
            std::cout << "  " << key << ": " << value << "\n";
        }
    }

    void displayMetrics() const {
        if (results.empty()) {
            std::cout << "\nNo recovery results available.\n";
            return;
        }

        int rpoPassed = 0;
        int rtoPassed = 0;

        for (const auto& result : results) {
            rpoPassed += result.rpoMet;
            rtoPassed += result.rtoMet;
        }

        const double count = results.size();

        std::cout << std::fixed << std::setprecision(2);

        std::cout
            << "\nRecovery Metrics\n"
            << "Total recoveries: " << results.size() << "\n"
            << "RPO compliance: "
            << (100.0 * rpoPassed / count) << "%\n"
            << "RTO compliance: "
            << (100.0 * rtoPassed / count) << "%\n";
    }

    void listBackups(const std::string& systemName) const {
        std::cout << "\nBackup Inventory\n";

        for (const auto& [id, backup] : backups) {
            if (backup.system == systemName) {
                std::cout
                    << id << " | "
                    << toString(backup.type) << " | "
                    << toString(backup.state) << " | "
                    << (backup.offsite ? "OFFSITE" : "LOCAL")
                    << "\n";
            }
        }
    }

    void enforceRetention(
        const std::string& systemName,
        TimePoint reference
    ) {
        const auto& system = getSystem(systemName);

        const auto cutoff = reference -
            std::chrono::hours(
                24 * system.policy.retentionDays
            );

        std::set<std::string> referencedParents;

        for (const auto& [id, backup] : backups) {
            if (backup.parentId.has_value()) {
                referencedParents.insert(
                    backup.parentId.value()
                );
            }
        }

        for (auto it = backups.begin(); it != backups.end();) {
            const auto& backup = it->second;

            if (
                backup.system == systemName &&
                backup.createdAt < cutoff &&
                !referencedParents.count(backup.id)
            ) {
                it = backups.erase(it);
            } else {
                ++it;
            }
        }
    }
};


int main() {
    try {
        DisasterRecoveryEngine engine;

        RecoveryPolicy policy{
            "Banking Critical Infrastructure",
            15,
            30,
            30,
            true,
            2
        };

        engine.registerSystem(
            "banking-primary",
            {
                {"accounts", 25000},
                {"transactions", 150000},
                {"balance_inr", 750000000}
            },
            policy
        );

        const std::string fullBackup =
            engine.createBackup(
                "banking-primary",
                BackupType::FULL,
                true
            );

        engine.updateSystem(
            "banking-primary",
            {
                {"transactions", 150100},
                {"balance_inr", 752000000}
            }
        );

        const std::string incrementalBackup =
            engine.createBackup(
                "banking-primary",
                BackupType::INCREMENTAL,
                true
            );

        const TimePoint incidentTime = Clock::now();

        const std::string incident =
            engine.createIncident(
                "banking-primary",
                Severity::CRITICAL,
                incidentTime
            );

        engine.updateSystem(
            "banking-primary",
            {
                {"accounts", 0},
                {"transactions", 0},
                {"balance_inr", 0}
            }
        );

        std::cout << "Disaster Recovery Simulation\n";
        std::cout << "============================\n";

        engine.listBackups("banking-primary");

        auto decision = engine.evaluateEligibility(
            incident,
            2,
            incrementalBackup
        );

        if (!decision.eligible) {
            std::cout << "\nRecovery blocked:\n";

            for (const auto& violation : decision.violations) {
                std::cout << "- " << violation << "\n";
            }

            return 1;
        }

        std::cout
            << "\nSelected backup: "
            << decision.selectedBackup.value()
            << "\n";

        const RecoveryResult result = engine.restore(
            incident,
            2,
            incrementalBackup
        );

        engine.displaySystem("banking-primary");
        engine.displayMetrics();

        std::cout << std::fixed << std::setprecision(4);

        std::cout
            << "\nRecovery Assessment\n"
            << "Actual RPO: "
            << result.actualRpoMinutes << " minutes\n"
            << "Actual RTO: "
            << result.actualRtoMinutes << " minutes\n"
            << "RPO met: "
            << (result.rpoMet ? "YES" : "NO") << "\n"
            << "RTO met: "
            << (result.rtoMet ? "YES" : "NO") << "\n"
            << "Recovery successful: "
            << (result.successful ? "YES" : "NO") << "\n";

        // A backup may restore successfully without meeting its RPO.
        // Eligibility and successful data restoration are separate
        // decisions in operational recovery systems.

        (void)fullBackup;

    } catch (const std::exception& error) {
        std::cerr
            << "Recovery engine error: "
            << error.what()
            << "\n";

        return 1;
    }

    return 0;
}
