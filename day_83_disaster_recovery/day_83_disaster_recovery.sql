import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/*
 * Disaster Recovery Governance Platform
 *
 * Java 17
 * Standard library only.
 *
 * Enterprise-oriented domain model for backup management,
 * recovery authorization, restoration, and RPO/RTO compliance.
 */

public class DisasterRecovery {

    enum BackupType {
        FULL,
        INCREMENTAL,
        DIFFERENTIAL
    }

    enum BackupStatus {
        CREATED,
        VERIFIED,
        FAILED,
        RESTORED
    }

    enum IncidentStatus {
        OPEN,
        RECOVERING,
        RECOVERED,
        FAILED
    }

    enum Severity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    enum RecoveryAction {
        RESTORE,
        FAILOVER,
        POINT_IN_TIME_RECOVERY
    }

    static class RecoveryException extends RuntimeException {
        RecoveryException(String message) {
            super(message);
        }
    }

    record RecoveryPolicy(
        String name,
        long rpoMinutes,
        long rtoMinutes,
        int retentionDays,
        boolean requireOffsite,
        int minimumApprovals,
        boolean requireIntegrityVerification
    ) {
        RecoveryPolicy {
            Objects.requireNonNull(name);

            if (name.isBlank() ||
                rpoMinutes < 0 ||
                rtoMinutes <= 0 ||
                retentionDays <= 0 ||
                minimumApprovals < 1) {
                throw new IllegalArgumentException(
                    "Invalid recovery policy"
                );
            }
        }
    }

    record RecoveryApproval(
        String reviewer,
        String role,
        Instant approvedAt
    ) {
        RecoveryApproval {
            Objects.requireNonNull(reviewer);
            Objects.requireNonNull(role);
            Objects.requireNonNull(approvedAt);

            if (reviewer.isBlank() || role.isBlank()) {
                throw new IllegalArgumentException(
                    "Reviewer and role are required"
                );
            }
        }
    }

    record RecoveryResult(
        String incidentId,
        String backupId,
        Instant startedAt,
        Instant completedAt,
        double actualRpoMinutes,
        double actualRtoMinutes,
        boolean rpoMet,
        boolean rtoMet,
        boolean successful
    ) {}

    static final class Backup {
        private final String id;
        private final String systemName;
        private final BackupType type;
        private final Instant createdAt;
        private final Map<String, Long> snapshot;
        private final String checksum;
        private final boolean offsite;
        private final String parentId;

        private BackupStatus status;

        Backup(
            String systemName,
            BackupType type,
            Map<String, Long> snapshot,
            String checksum,
            boolean offsite,
            String parentId
        ) {
            this.id = UUID.randomUUID().toString();
            this.systemName = systemName;
            this.type = type;
            this.createdAt = Instant.now();
            this.snapshot = Map.copyOf(snapshot);
            this.checksum = checksum;
            this.offsite = offsite;
            this.parentId = parentId;
            this.status = BackupStatus.CREATED;
        }

        String id() {
            return id;
        }

        String systemName() {
            return systemName;
        }

        BackupType type() {
            return type;
        }

        Instant createdAt() {
            return createdAt;
        }

        Map<String, Long> snapshot() {
            return snapshot;
        }

        String checksum() {
            return checksum;
        }

        boolean offsite() {
            return offsite;
        }

        String parentId() {
            return parentId;
        }

        BackupStatus status() {
            return status;
        }

        void setStatus(BackupStatus status) {
            this.status = status;
        }
    }

    static final class ProtectedSystem {
        private final String name;
        private final RecoveryPolicy policy;
        private Map<String, Long> data;
        private Instant modifiedAt;

        ProtectedSystem(
            String name,
            Map<String, Long> initialData,
            RecoveryPolicy policy
        ) {
            this.name = name;
            this.data = new HashMap<>(initialData);
            this.policy = policy;
            this.modifiedAt = Instant.now();
        }

        String name() {
            return name;
        }

        RecoveryPolicy policy() {
            return policy;
        }

        Map<String, Long> getData() {
            return Map.copyOf(data);
        }

        void update(Map<String, Long> updates) {
            data.putAll(updates);
            modifiedAt = Instant.now();
        }

        void restore(Map<String, Long> snapshot, Instant timestamp) {
            // Replace application state only after staging validation.
            data = new HashMap<>(snapshot);
            modifiedAt = timestamp;
        }
    }

    static final class Incident {
        private final String id;
        private final String systemName;
        private final Severity severity;
        private final Instant occurredAt;
        private final List<RecoveryApproval> approvals =
            new ArrayList<>();

        private IncidentStatus status = IncidentStatus.OPEN;

        Incident(
            String systemName,
            Severity severity,
            Instant occurredAt
        ) {
            this.id = UUID.randomUUID().toString();
            this.systemName = systemName;
            this.severity = severity;
            this.occurredAt = occurredAt;
        }

        String id() {
            return id;
        }

        String systemName() {
            return systemName;
        }

        Instant occurredAt() {
            return occurredAt;
        }

        IncidentStatus status() {
            return status;
        }

        void setStatus(IncidentStatus status) {
            this.status = status;
        }

        List<RecoveryApproval> approvals() {
            return List.copyOf(approvals);
        }

        void addApproval(RecoveryApproval approval) {
            if (status != IncidentStatus.OPEN) {
                throw new RecoveryException(
                    "Approvals cannot change after recovery begins"
                );
            }

            boolean duplicate = approvals.stream().anyMatch(
                existing ->
                    existing.reviewer().equalsIgnoreCase(
                        approval.reviewer()
                    )
            );

            if (duplicate) {
                throw new RecoveryException(
                    "Duplicate recovery approval"
                );
            }

            approvals.add(approval);
        }
    }

    record EligibilityDecision(
        boolean eligible,
        Optional<String> backupId,
        List<String> violations,
        double actualRpoMinutes
    ) {
        EligibilityDecision {
            backupId = backupId == null
                ? Optional.empty()
                : backupId;

            violations = List.copyOf(violations);
        }
    }

    static final class RecoveryAuthorizationService {

        private static final Set<String> AUTHORIZED_ROLES = Set.of(
            "OPERATIONS_MANAGER",
            "SECURITY_MANAGER",
            "DISASTER_RECOVERY_MANAGER"
        );

        void authorize(Incident incident, RecoveryPolicy policy) {
            List<RecoveryApproval> approvals =
                incident.approvals();

            Set<String> reviewers = approvals.stream()
                .map(approval ->
                    approval.reviewer().toLowerCase()
                )
                .collect(Collectors.toSet());

            Set<String> authorizedReviewers = approvals.stream()
                .filter(approval ->
                    AUTHORIZED_ROLES.contains(approval.role())
                )
                .map(approval ->
                    approval.reviewer().toLowerCase()
                )
                .collect(Collectors.toSet());

            if (reviewers.size() < policy.minimumApprovals()) {
                throw new RecoveryException(
                    "Minimum approval count not satisfied"
                );
            }

            if (
                authorizedReviewers.size() <
                policy.minimumApprovals()
            ) {
                throw new RecoveryException(
                    "Approvals from authorized roles are insufficient"
                );
            }
        }
    }

    static final class BackupService {

        private final Map<String, Backup> backups = new HashMap<>();

        private String checksum(Map<String, Long> snapshot) {
            /*
             * SHA-256 over a deterministic representation.
             * Production implementations should use a versioned,
             * canonical serialization format.
             */
            try {
                var digest = java.security.MessageDigest.getInstance(
                    "SHA-256"
                );

                String canonical = snapshot.entrySet().stream()
                    .sorted(Map.Entry.comparingByKey())
                    .map(entry ->
                        entry.getKey() + "=" + entry.getValue()
                    )
                    .collect(Collectors.joining(";"));

                byte[] hash = digest.digest(
                    canonical.getBytes(
                        java.nio.charset.StandardCharsets.UTF_8
                    )
                );

                return java.util.HexFormat.of().formatHex(hash);

            } catch (java.security.NoSuchAlgorithmException error) {
                throw new IllegalStateException(error);
            }
        }

        Backup create(
            ProtectedSystem system,
            BackupType type,
            boolean offsite
        ) {
            if (
                system.policy().requireOffsite() &&
                !offsite
            ) {
                throw new RecoveryException(
                    "Offsite backup is mandatory"
                );
            }

            Optional<Backup> parent = backups.values().stream()
                .filter(backup ->
                    backup.systemName().equals(system.name()) &&
                    backup.status() == BackupStatus.VERIFIED
                )
                .max(Comparator.comparing(Backup::createdAt));

            if (
                type == BackupType.INCREMENTAL &&
                parent.isEmpty()
            ) {
                throw new RecoveryException(
                    "Incremental backup requires a verified parent"
                );
            }

            Map<String, Long> snapshot = system.getData();

            Backup backup = new Backup(
                system.name(),
                type,
                snapshot,
                checksum(snapshot),
                offsite,
                type == BackupType.INCREMENTAL
                    ? parent.get().id()
                    : null
            );

            backups.put(backup.id(), backup);

            verify(backup.id());

            return backup;
        }

        void verify(String backupId) {
            Backup backup = requireBackup(backupId);

            if (!checksum(backup.snapshot()).equals(
                backup.checksum()
            )) {
                backup.setStatus(BackupStatus.FAILED);

                throw new RecoveryException(
                    "Backup integrity verification failed"
                );
            }

            backup.setStatus(BackupStatus.VERIFIED);
        }

        Backup requireBackup(String id) {
            Backup backup = backups.get(id);

            if (backup == null) {
                throw new RecoveryException(
                    "Backup does not exist"
                );
            }

            return backup;
        }

        List<Backup> listForSystem(String systemName) {
            return backups.values().stream()
                .filter(backup ->
                    backup.systemName().equals(systemName)
                )
                .sorted(
                    Comparator.comparing(Backup::createdAt)
                )
                .toList();
        }
    }

    static final class RecoveryEligibilityService {

        EligibilityDecision evaluate(
            Incident incident,
            ProtectedSystem system,
            List<Backup> availableBackups,
            String requestedBackup
        ) {
            List<String> violations = new ArrayList<>();

            if (incident.status() != IncidentStatus.OPEN) {
                violations.add("Incident is not open");
            }

            Optional<Backup> selected = availableBackups.stream()
                .filter(backup ->
                    requestedBackup == null ||
                    backup.id().equals(requestedBackup)
                )
                .filter(backup ->
                    backup.status() == BackupStatus.VERIFIED
                )
                .filter(backup ->
                    backup.createdAt().compareTo(
                        incident.occurredAt()
                    ) <= 0
                )
                .filter(backup ->
                    !system.policy().requireOffsite() ||
                    backup.offsite()
                )
                .max(Comparator.comparing(Backup::createdAt));

            if (selected.isEmpty()) {
                violations.add("No eligible backup exists");

                return new EligibilityDecision(
                    false,
                    Optional.empty(),
                    violations,
                    Double.NaN
                );
            }

            double actualRpo = Duration.between(
                selected.get().createdAt(),
                incident.occurredAt()
            ).toMillis() / 60000.0;

            if (actualRpo > system.policy().rpoMinutes()) {
                violations.add("RPO requirement cannot be satisfied");
            }

            return new EligibilityDecision(
                violations.isEmpty(),
                Optional.of(selected.get().id()),
                violations,
                actualRpo
            );
        }
    }

    static final class RecoveryService {

        private final BackupService backupService;
        private final RecoveryAuthorizationService authorization;
        private final RecoveryEligibilityService eligibility;

        private final Map<String, ProtectedSystem> systems =
            new HashMap<>();

        private final Map<String, Incident> incidents =
            new HashMap<>();

        private final List<RecoveryResult> results =
            new ArrayList<>();

        RecoveryService(
            BackupService backupService,
            RecoveryAuthorizationService authorization,
            RecoveryEligibilityService eligibility
        ) {
            this.backupService = backupService;
            this.authorization = authorization;
            this.eligibility = eligibility;
        }

        void register(ProtectedSystem system) {
            if (systems.putIfAbsent(system.name(), system) != null) {
                throw new RecoveryException(
                    "Duplicate protected system"
                );
            }
        }

        Incident reportIncident(
            String systemName,
            Severity severity,
            Instant occurredAt
        ) {
            if (!systems.containsKey(systemName)) {
                throw new RecoveryException(
                    "Unknown protected system"
                );
            }

            Incident incident = new Incident(
                systemName,
                severity,
                occurredAt
            );

            incidents.put(incident.id(), incident);

            return incident;
        }

        RecoveryResult recover(
            String incidentId,
            String backupId
        ) {
            Incident incident = incidents.get(incidentId);

            if (incident == null) {
                throw new RecoveryException(
                    "Incident not found"
                );
            }

            ProtectedSystem system =
                systems.get(incident.systemName());

            authorization.authorize(
                incident,
                system.policy()
            );

            EligibilityDecision decision =
                eligibility.evaluate(
                    incident,
                    system,
                    backupService.listForSystem(system.name()),
                    backupId
                );

            if (!decision.eligible()) {
                throw new RecoveryException(
                    String.join("; ", decision.violations())
                );
            }

            incident.setStatus(IncidentStatus.RECOVERING);

            Instant started = Instant.now();

            try {
                Backup backup = backupService.requireBackup(
                    decision.backupId().orElseThrow()
                );

                backupService.verify(backup.id());

                // Prepare replacement state before committing restoration.
                Map<String, Long> staged = Map.copyOf(
                    backup.snapshot()
                );

                if (staged.isEmpty()) {
                    throw new RecoveryException(
                        "Empty snapshot rejected"
                    );
                }

                system.restore(staged, backup.createdAt());

                backup.setStatus(BackupStatus.RESTORED);
                incident.setStatus(IncidentStatus.RECOVERED);

                Instant completed = Instant.now();

                double actualRto = Duration.between(
                    started,
                    completed
                ).toMillis() / 60000.0;

                RecoveryResult result = new RecoveryResult(
                    incident.id(),
                    backup.id(),
                    started,
                    completed,
                    decision.actualRpoMinutes(),
                    actualRto,
                    decision.actualRpoMinutes() <=
                        system.policy().rpoMinutes(),
                    actualRto <= system.policy().rtoMinutes(),
                    true
                );

                results.add(result);

                return result;

            } catch (RuntimeException error) {
                incident.setStatus(IncidentStatus.FAILED);
                throw error;
            }
        }

        List<RecoveryResult> results() {
            return List.copyOf(results);
        }

        Map<String, Double> metrics() {
            if (results.isEmpty()) {
                return Map.of(
                    "rpoCompliancePercent", 0.0,
                    "rtoCompliancePercent", 0.0
                );
            }

            long rpoPassed = results.stream()
                .filter(RecoveryResult::rpoMet)
                .count();

            long rtoPassed = results.stream()
                .filter(RecoveryResult::rtoMet)
                .count();

            double count = results.size();

            return Map.of(
                "rpoCompliancePercent",
                100.0 * rpoPassed / count,
                "rtoCompliancePercent",
                100.0 * rtoPassed / count
            );
        }

        ProtectedSystem getSystem(String name) {
            ProtectedSystem system = systems.get(name);

            if (system == null) {
                throw new RecoveryException(
                    "Protected system not found"
                );
            }

            return system;
        }
    }

    public static void main(String[] args) {

        RecoveryPolicy policy = new RecoveryPolicy(
            "Enterprise Banking Recovery",
            15,
            30,
            30,
            true,
            2,
            true
        );

        ProtectedSystem banking = new ProtectedSystem(
            "banking-production",
            Map.of(
                "accounts", 25000L,
                "transactions", 150000L,
                "balanceInr", 750000000L
            ),
            policy
        );

        BackupService backupService = new BackupService();

        RecoveryAuthorizationService authorization =
            new RecoveryAuthorizationService();

        RecoveryEligibilityService eligibility =
            new RecoveryEligibilityService();

        RecoveryService recoveryService = new RecoveryService(
            backupService,
            authorization,
            eligibility
        );

        recoveryService.register(banking);

        Backup fullBackup = backupService.create(
            banking,
            BackupType.FULL,
            true
        );

        banking.update(Map.of(
            "transactions", 150100L,
            "balanceInr", 752000000L
        ));

        Backup incremental = backupService.create(
            banking,
            BackupType.INCREMENTAL,
            true
        );

        Instant incidentTime = Instant.now();

        Incident incident = recoveryService.reportIncident(
            "banking-production",
            Severity.CRITICAL,
            incidentTime
        );

        incident.addApproval(
            new RecoveryApproval(
                "operations-lead",
                "OPERATIONS_MANAGER",
                Instant.now()
            )
        );

        incident.addApproval(
            new RecoveryApproval(
                "security-lead",
                "SECURITY_MANAGER",
                Instant.now()
            )
        );

        // Simulate complete production data loss.
        banking.update(Map.of(
            "accounts", 0L,
            "transactions", 0L,
            "balanceInr", 0L
        ));

        RecoveryResult result = recoveryService.recover(
            incident.id(),
            incremental.id()
        );

        System.out.println("DISASTER RECOVERY REPORT");
        System.out.println("=========================");

        System.out.println(
            "Incident: " + result.incidentId()
        );

        System.out.println(
            "Selected backup: " + result.backupId()
        );

        System.out.println(
            "RPO: " + result.actualRpoMinutes() + " minutes"
        );

        System.out.println(
            "RTO: " + result.actualRtoMinutes() + " minutes"
        );

        System.out.println(
            "RPO met: " + result.rpoMet()
        );

        System.out.println(
            "RTO met: " + result.rtoMet()
        );

        System.out.println(
            "Restored data: " +
            recoveryService.getSystem(
                "banking-production"
            ).getData()
        );

        System.out.println(
            "Compliance: " + recoveryService.metrics()
        );

        System.out.println(
            "Previous full backup: " + fullBackup.id()
        );
    }
}
