"use strict";

/*
 * Disaster Recovery and Business Continuity Engine
 * Node.js 18+
 *
 * Implements event-driven backup scheduling, recovery policies,
 * backup integrity validation, restoration, and RPO/RTO evaluation.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");

const BackupType = Object.freeze({
    FULL: "FULL",
    INCREMENTAL: "INCREMENTAL",
    DIFFERENTIAL: "DIFFERENTIAL"
});

const BackupState = Object.freeze({
    CREATED: "CREATED",
    VERIFIED: "VERIFIED",
    FAILED: "FAILED",
    RESTORED: "RESTORED"
});

const IncidentState = Object.freeze({
    PENDING: "PENDING",
    RECOVERING: "RECOVERING",
    RECOVERED: "RECOVERED",
    FAILED: "FAILED"
});


class RecoveryError extends Error {
    constructor(message, code) {
        super(message);
        this.name = "RecoveryError";
        this.code = code;
    }
}


class RecoveryPolicy {
    constructor({
        name,
        rpoMinutes,
        rtoMinutes,
        retentionDays,
        requireOffsite = true,
        minimumApprovals = 1
    }) {
        if (!Number.isFinite(rpoMinutes) || rpoMinutes < 0) {
            throw new TypeError("RPO must be a non-negative number");
        }

        if (!Number.isFinite(rtoMinutes) || rtoMinutes <= 0) {
            throw new TypeError("RTO must be positive");
        }

        if (!Number.isInteger(retentionDays) || retentionDays < 1) {
            throw new TypeError("Retention must be a positive integer");
        }

        if (!Number.isInteger(minimumApprovals) ||
            minimumApprovals < 1) {
            throw new TypeError("At least one approval is required");
        }

        this.name = name;
        this.rpoMinutes = rpoMinutes;
        this.rtoMinutes = rtoMinutes;
        this.retentionDays = retentionDays;
        this.requireOffsite = requireOffsite;
        this.minimumApprovals = minimumApprovals;

        Object.freeze(this);
    }
}


function canonicalize(value) {
    if (Array.isArray(value)) {
        return value.map(canonicalize);
    }

    if (value && typeof value === "object") {
        const result = {};

        for (const key of Object.keys(value).sort()) {
            result[key] = canonicalize(value[key]);
        }

        return result;
    }

    return value;
}


function checksum(data) {
    const serialized = JSON.stringify(canonicalize(data));

    return crypto
        .createHash("sha256")
        .update(serialized, "utf8")
        .digest("hex");
}


function deepClone(data) {
    return structuredClone(data);
}


class DisasterRecoveryEngine extends EventEmitter {
    #systems = new Map();
    #backups = new Map();
    #incidents = new Map();
    #recoveries = [];

    constructor(storageDirectory) {
        super();

        this.storageDirectory = path.resolve(storageDirectory);

        this.on("backup.created", event => {
            console.log(
                `[EVENT] Backup created: ${event.backupId}`
            );
        });

        this.on("recovery.completed", event => {
            console.log(
                `[EVENT] Recovery completed: ${event.incidentId}`
            );
        });
    }

    async initialize() {
        await fs.mkdir(this.storageDirectory, {
            recursive: true,
            mode: 0o700
        });
    }

    registerSystem(name, data, policy) {
        if (!name || this.#systems.has(name)) {
            throw new RecoveryError(
                "Invalid or duplicate system",
                "SYSTEM_REGISTRATION_ERROR"
            );
        }

        if (!data || typeof data !== "object" ||
            Array.isArray(data)) {
            throw new TypeError("System data must be an object");
        }

        if (!(policy instanceof RecoveryPolicy)) {
            throw new TypeError("A valid recovery policy is required");
        }

        this.#systems.set(name, {
            name,
            data: deepClone(data),
            policy,
            modifiedAt: new Date()
        });
    }

    updateSystem(name, changes) {
        const system = this.#requireSystem(name);

        if (!changes || typeof changes !== "object" ||
            Array.isArray(changes)) {
            throw new TypeError("Changes must be an object");
        }

        system.data = {
            ...system.data,
            ...deepClone(changes)
        };

        system.modifiedAt = new Date();
    }

    #requireSystem(name) {
        const system = this.#systems.get(name);

        if (!system) {
            throw new RecoveryError(
                `System not found: ${name}`,
                "SYSTEM_NOT_FOUND"
            );
        }

        return system;
    }

    #requireBackup(id) {
        const backup = this.#backups.get(id);

        if (!backup) {
            throw new RecoveryError(
                `Backup not found: ${id}`,
                "BACKUP_NOT_FOUND"
            );
        }

        return backup;
    }

    async createBackup(name, type = BackupType.FULL, offsite = true) {
        const system = this.#requireSystem(name);

        if (!Object.values(BackupType).includes(type)) {
            throw new TypeError("Unsupported backup type");
        }

        if (system.policy.requireOffsite && !offsite) {
            throw new RecoveryError(
                "Offsite backup required",
                "OFFSITE_POLICY_VIOLATION"
            );
        }

        const existing = [...this.#backups.values()]
            .filter(item =>
                item.systemName === name &&
                item.state === BackupState.VERIFIED
            )
            .sort((a, b) =>
                b.createdAt.getTime() - a.createdAt.getTime()
            );

        if (type === BackupType.INCREMENTAL && existing.length === 0) {
            throw new RecoveryError(
                "Incremental backup requires a verified parent",
                "MISSING_PARENT_BACKUP"
            );
        }

        const backup = {
            id: crypto.randomUUID(),
            systemName: name,
            type,
            createdAt: new Date(),
            data: deepClone(system.data),
            digest: checksum(system.data),
            state: BackupState.CREATED,
            offsite,
            parentId: type === BackupType.INCREMENTAL
                ? existing[0].id
                : null
        };

        this.#backups.set(backup.id, backup);

        try {
            await this.#persist(backup);
            this.verifyBackup(backup.id);

            this.emit("backup.created", {
                backupId: backup.id,
                systemName: name,
                type
            });

            return this.#publicBackup(backup);

        } catch (error) {
            backup.state = BackupState.FAILED;
            throw error;
        }
    }

    async #persist(backup) {
        const destination = path.join(
            this.storageDirectory,
            `${backup.id}.json`
        );

        const temporary = `${destination}.tmp`;

        const payload = {
            ...backup,
            createdAt: backup.createdAt.toISOString()
        };

        try {
            await fs.writeFile(
                temporary,
                JSON.stringify(payload, null, 2),
                {
                    encoding: "utf8",
                    flag: "wx",
                    mode: 0o600
                }
            );

            await fs.rename(temporary, destination);

        } catch (error) {
            await fs.rm(temporary, { force: true });
            throw error;
        }
    }

    verifyBackup(id) {
        const backup = this.#requireBackup(id);

        if (checksum(backup.data) !== backup.digest) {
            backup.state = BackupState.FAILED;

            throw new RecoveryError(
                "Backup integrity check failed",
                "CHECKSUM_MISMATCH"
            );
        }

        backup.state = BackupState.VERIFIED;

        return true;
    }

    #publicBackup(backup) {
        return Object.freeze({
            id: backup.id,
            systemName: backup.systemName,
            type: backup.type,
            createdAt: backup.createdAt.toISOString(),
            state: backup.state,
            offsite: backup.offsite,
            parentId: backup.parentId,
            digest: backup.digest
        });
    }

    createIncident(name, description, severity, occurredAt = new Date()) {
        this.#requireSystem(name);

        const timestamp = new Date(occurredAt);

        if (Number.isNaN(timestamp.getTime())) {
            throw new TypeError("Invalid incident timestamp");
        }

        const incident = {
            id: crypto.randomUUID(),
            systemName: name,
            description,
            severity,
            occurredAt: timestamp,
            state: IncidentState.PENDING
        };

        this.#incidents.set(incident.id, incident);

        this.emit("incident.registered", {
            incidentId: incident.id,
            severity
        });

        return Object.freeze({ ...incident });
    }

    async restore(incidentId, backupId = null, options = {}) {
        const incident = this.#incidents.get(incidentId);

        if (!incident) {
            throw new RecoveryError(
                "Incident not found",
                "INCIDENT_NOT_FOUND"
            );
        }

        if (incident.state !== IncidentState.PENDING) {
            throw new RecoveryError(
                "Incident cannot be recovered in its current state",
                "INVALID_INCIDENT_STATE"
            );
        }

        const system = this.#requireSystem(incident.systemName);

        const approvals = new Set(options.approvers || []);

        if (approvals.size < system.policy.minimumApprovals) {
            throw new RecoveryError(
                "Insufficient independent recovery approvals",
                "APPROVAL_REQUIREMENT_NOT_MET"
            );
        }

        let candidates = [...this.#backups.values()]
            .filter(backup =>
                backup.systemName === incident.systemName &&
                backup.state === BackupState.VERIFIED &&
                backup.createdAt <= incident.occurredAt &&
                (
                    !system.policy.requireOffsite ||
                    backup.offsite
                )
            );

        if (backupId) {
            candidates = candidates.filter(
                backup => backup.id === backupId
            );
        }

        candidates.sort((a, b) =>
            b.createdAt.getTime() - a.createdAt.getTime()
        );

        const selected = candidates[0];

        if (!selected) {
            incident.state = IncidentState.FAILED;

            throw new RecoveryError(
                "No eligible backup exists",
                "NO_ELIGIBLE_BACKUP"
            );
        }

        incident.state = IncidentState.RECOVERING;

        const startedAt = new Date();

        try {
            this.verifyBackup(selected.id);

            // Stage and validate data before switching active state.
            const stagedData = deepClone(selected.data);

            if (!stagedData ||
                typeof stagedData !== "object" ||
                Array.isArray(stagedData)) {
                throw new RecoveryError(
                    "Invalid backup payload",
                    "INVALID_BACKUP_PAYLOAD"
                );
            }

            system.data = stagedData;
            system.modifiedAt = selected.createdAt;

            selected.state = BackupState.RESTORED;
            incident.state = IncidentState.RECOVERED;

        } catch (error) {
            incident.state = IncidentState.FAILED;
            throw error;
        }

        const completedAt = new Date();

        const actualRpo =
            Math.max(
                0,
                incident.occurredAt.getTime() -
                selected.createdAt.getTime()
            ) / 60000;

        const actualRto =
            (completedAt.getTime() - startedAt.getTime()) / 60000;

        const result = Object.freeze({
            incidentId,
            backupId: selected.id,
            startedAt: startedAt.toISOString(),
            completedAt: completedAt.toISOString(),
            actualRpoMinutes: actualRpo,
            actualRtoMinutes: actualRto,
            rpoMet: actualRpo <= system.policy.rpoMinutes,
            rtoMet: actualRto <= system.policy.rtoMinutes,
            successful: true
        });

        this.#recoveries.push(result);

        this.emit("recovery.completed", result);

        return result;
    }

    async verifyAllBackups() {
        const results = [];

        for (const backup of this.#backups.values()) {
            try {
                this.verifyBackup(backup.id);

                results.push({
                    id: backup.id,
                    valid: true
                });

            } catch (error) {
                results.push({
                    id: backup.id,
                    valid: false,
                    error: error.message
                });
            }
        }

        return results;
    }

    enforceRetention(name, referenceDate = new Date()) {
        const system = this.#requireSystem(name);

        const cutoff =
            referenceDate.getTime() -
            system.policy.retentionDays * 86400000;

        let removed = 0;

        for (const [id, backup] of this.#backups) {
            if (
                backup.systemName === name &&
                backup.createdAt.getTime() < cutoff &&
                ![...this.#backups.values()].some(
                    child => child.parentId === id
                )
            ) {
                this.#backups.delete(id);
                removed++;
            }
        }

        return removed;
    }

    getRecoveryMetrics() {
        const total = this.#recoveries.length;

        if (total === 0) {
            return {
                total: 0,
                rpoCompliance: 0,
                rtoCompliance: 0
            };
        }

        const rpoPassed = this.#recoveries.filter(
            item => item.rpoMet
        ).length;

        const rtoPassed = this.#recoveries.filter(
            item => item.rtoMet
        ).length;

        return {
            total,
            rpoCompliance: Number(
                (100 * rpoPassed / total).toFixed(2)
            ),
            rtoCompliance: Number(
                (100 * rtoPassed / total).toFixed(2)
            ),
            averageRpoMinutes:
                this.#recoveries.reduce(
                    (sum, item) => sum + item.actualRpoMinutes,
                    0
                ) / total,
            averageRtoMinutes:
                this.#recoveries.reduce(
                    (sum, item) => sum + item.actualRtoMinutes,
                    0
                ) / total
        };
    }

    getSystemData(name) {
        return deepClone(this.#requireSystem(name).data);
    }
}


async function main() {
    const storage = path.join(
        process.cwd(),
        "disaster-recovery-backups"
    );

    const engine = new DisasterRecoveryEngine(storage);

    await engine.initialize();

    const policy = new RecoveryPolicy({
        name: "Production Banking Platform",
        rpoMinutes: 15,
        rtoMinutes: 30,
        retentionDays: 30,
        requireOffsite: true,
        minimumApprovals: 2
    });

    engine.registerSystem(
        "banking",
        {
            accounts: 25000,
            transactions: 150000,
            balance: 750000000
        },
        policy
    );

    const backup = await engine.createBackup(
        "banking",
        BackupType.FULL,
        true
    );

    engine.updateSystem("banking", {
        transactions: 150100,
        balance: 752000000
    });

    const incidentTime = new Date(
        new Date(backup.createdAt).getTime() + 5 * 60000
    );

    const incident = engine.createIncident(
        "banking",
        "Primary database cluster unavailable",
        "CRITICAL",
        incidentTime
    );

    engine.updateSystem("banking", {
        accounts: 0,
        transactions: 0,
        balance: 0
    });

    const recovery = await engine.restore(
        incident.id,
        backup.id,
        {
            approvers: ["operations-manager", "security-manager"]
        }
    );

    console.log("\nRECOVERY RESULT");
    console.log(JSON.stringify(recovery, null, 2));

    console.log("\nRESTORED SYSTEM");
    console.log(JSON.stringify(
        engine.getSystemData("banking"),
        null,
        2
    ));

    console.log("\nRECOVERY METRICS");
    console.log(JSON.stringify(
        engine.getRecoveryMetrics(),
        null,
        2
    ));

    console.log("\nBACKUP VALIDATION");
    console.log(JSON.stringify(
        await engine.verifyAllBackups(),
        null,
        2
    ));
}

main().catch(error => {
    console.error("Disaster recovery failure:", error);
    process.exitCode = 1;
});
