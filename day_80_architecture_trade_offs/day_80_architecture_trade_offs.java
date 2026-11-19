import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * Enterprise Architecture Trade-off Management System.
 *
 * Java 17 implementation featuring:
 * - Immutable domain records
 * - Architecture catalogs
 * - Workload profiles
 * - Cost estimation
 * - Reliability engineering
 * - Dependency management
 * - Risk assessment
 * - Architecture decision policies
 * - Hard governance constraints
 * - Weighted scoring
 * - Pareto analysis
 * - Decision audit history
 *
 * Compile:
 * javac --release 17 ArchitectureTradeoffs.java
 *
 * Run:
 * java ArchitectureTradeoffs
 */
public class ArchitectureTradeoffs {

    enum ArchitectureType {
        MONOLITH,
        MODULAR_MONOLITH,
        MICROSERVICES,
        SERVERLESS,
        EVENT_DRIVEN,
        HYBRID
    }

    enum DecisionStatus {
        PROPOSED,
        ACCEPTED,
        REJECTED,
        SUPERSEDED
    }

    enum RiskCategory {
        FINANCIAL,
        PERFORMANCE,
        RELIABILITY,
        SECURITY,
        OPERATIONAL,
        VENDOR_LOCK_IN
    }

    enum Severity {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    record ArchitectureMetrics(
        double infrastructureCost,
        double operationsCost,
        double latencyMs,
        double throughputRps,
        double availabilityPercent,
        double complexity,
        double scalability,
        double recoveryTimeMinutes
    ) {
        ArchitectureMetrics {
            requireNonNegative("Infrastructure cost", infrastructureCost);
            requireNonNegative("Operations cost", operationsCost);
            requireNonNegative("Latency", latencyMs);
            requireNonNegative("Throughput", throughputRps);
            requireNonNegative("Recovery time", recoveryTimeMinutes);

            if (!Double.isFinite(availabilityPercent) ||
                availabilityPercent <= 0 ||
                availabilityPercent > 100) {
                throw new IllegalArgumentException(
                    "Availability must be in (0, 100]"
                );
            }

            if (!Double.isFinite(complexity) ||
                complexity < 1 || complexity > 10) {
                throw new IllegalArgumentException(
                    "Complexity must be in [1, 10]"
                );
            }

            if (!Double.isFinite(scalability) ||
                scalability < 1 || scalability > 10) {
                throw new IllegalArgumentException(
                    "Scalability must be in [1, 10]"
                );
            }
        }

        double monthlyCost() {
            return infrastructureCost + operationsCost;
        }

        double annualCost() {
            return monthlyCost() * 12;
        }
    }

    record WorkloadProfile(
        String name,
        double averageRequestsPerSecond,
        double peakMultiplier,
        double payloadKilobytes,
        int concurrentUsers,
        double latencySlaMs
    ) {
        WorkloadProfile {
            Objects.requireNonNull(name);

            if (name.isBlank()) {
                throw new IllegalArgumentException("Workload name is required");
            }

            requireNonNegative("Average requests", averageRequestsPerSecond);
            requireAtLeast("Peak multiplier", peakMultiplier, 1);
            requireNonNegative("Payload", payloadKilobytes);
            requireNonNegative("Concurrent users", concurrentUsers);
            requireAtLeast("Latency SLA", latencySlaMs, 1);
        }

        double peakRequestsPerSecond() {
            return averageRequestsPerSecond * peakMultiplier;
        }

        double ingressMbps() {
            return peakRequestsPerSecond() * payloadKilobytes * 8 / 1024;
        }
    }

    record Architecture(
        String id,
        String name,
        ArchitectureType type,
        ArchitectureMetrics metrics,
        Set<String> dependencies,
        String deploymentModel
    ) {
        Architecture {
            Objects.requireNonNull(id);
            Objects.requireNonNull(name);
            Objects.requireNonNull(type);
            Objects.requireNonNull(metrics);
            Objects.requireNonNull(deploymentModel);

            if (id.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException(
                    "Architecture ID and name are required"
                );
            }

            dependencies = Set.copyOf(dependencies);
        }
    }

    record DecisionWeights(
        double cost,
        double performance,
        double reliability,
        double complexity,
        double scalability
    ) {
        DecisionWeights {
            double[] values = {
                cost,
                performance,
                reliability,
                complexity,
                scalability
            };

            double total = 0;

            for (double value : values) {
                if (!Double.isFinite(value) || value < 0) {
                    throw new IllegalArgumentException("Invalid weight");
                }

                total += value;
            }

            if (Math.abs(total - 1) > 1e-9) {
                throw new IllegalArgumentException(
                    "Weights must sum to one"
                );
            }
        }
    }

    record GovernancePolicy(
        double monthlyBudget,
        double minimumAvailability,
        double minimumThroughput,
        double maximumLatency,
        boolean requireDisasterRecovery
    ) {
        GovernancePolicy {
            requireNonNegative("Budget", monthlyBudget);
            requireNonNegative("Minimum throughput", minimumThroughput);

            if (minimumAvailability <= 0 ||
                minimumAvailability > 100 ||
                maximumLatency <= 0) {
                throw new IllegalArgumentException(
                    "Invalid governance thresholds"
                );
            }
        }
    }

    record Risk(
        String name,
        RiskCategory category,
        Severity severity,
        double annualProbability,
        double financialImpact
    ) {
        Risk {
            Objects.requireNonNull(name);
            Objects.requireNonNull(category);
            Objects.requireNonNull(severity);

            if (name.isBlank()) {
                throw new IllegalArgumentException("Risk name is required");
            }

            if (!Double.isFinite(annualProbability) ||
                annualProbability < 0 ||
                annualProbability > 1) {
                throw new IllegalArgumentException(
                    "Probability must be in [0, 1]"
                );
            }

            requireNonNegative("Financial impact", financialImpact);
        }

        double expectedAnnualLoss() {
            return annualProbability * financialImpact;
        }
    }

    record ArchitectureEvaluation(
        String architectureId,
        String architectureName,
        double monthlyCost,
        double annualCost,
        double availability,
        double annualDowntimeHours,
        double performanceScore,
        double costScore,
        double reliabilityScore,
        double complexityScore,
        double scalabilityScore,
        double weightedScore,
        boolean eligible,
        List<String> violations
    ) {
        ArchitectureEvaluation {
            violations = List.copyOf(violations);
        }
    }

    record ArchitectureDecision(
        String id,
        String title,
        String context,
        String selectedArchitectureId,
        List<String> alternatives,
        List<String> consequences,
        DecisionStatus status
    ) {
        ArchitectureDecision {
            Objects.requireNonNull(id);
            Objects.requireNonNull(title);
            Objects.requireNonNull(context);
            Objects.requireNonNull(selectedArchitectureId);
            Objects.requireNonNull(status);

            alternatives = List.copyOf(alternatives);
            consequences = List.copyOf(consequences);
        }
    }

    interface EvaluationRule {
        List<String> evaluate(
            Architecture architecture,
            WorkloadProfile workload,
            GovernancePolicy policy
        );
    }

    static class BudgetRule implements EvaluationRule {
        @Override
        public List<String> evaluate(
            Architecture architecture,
            WorkloadProfile workload,
            GovernancePolicy policy
        ) {
            if (architecture.metrics().monthlyCost() > policy.monthlyBudget()) {
                return List.of("MONTHLY_BUDGET_EXCEEDED");
            }

            return List.of();
        }
    }

    static class AvailabilityRule implements EvaluationRule {
        @Override
        public List<String> evaluate(
            Architecture architecture,
            WorkloadProfile workload,
            GovernancePolicy policy
        ) {
            if (architecture.metrics().availabilityPercent() <
                policy.minimumAvailability()) {
                return List.of("AVAILABILITY_REQUIREMENT_NOT_MET");
            }

            return List.of();
        }
    }

    static class CapacityRule implements EvaluationRule {
        @Override
        public List<String> evaluate(
            Architecture architecture,
            WorkloadProfile workload,
            GovernancePolicy policy
        ) {
            if (architecture.metrics().throughputRps() <
                Math.max(
                    policy.minimumThroughput(),
                    workload.peakRequestsPerSecond()
                )) {
                return List.of("CAPACITY_REQUIREMENT_NOT_MET");
            }

            return List.of();
        }
    }

    static class LatencyRule implements EvaluationRule {
        @Override
        public List<String> evaluate(
            Architecture architecture,
            WorkloadProfile workload,
            GovernancePolicy policy
        ) {
            if (architecture.metrics().latencyMs() >
                Math.min(
                    policy.maximumLatency(),
                    workload.latencySlaMs()
                )) {
                return List.of("LATENCY_SLA_VIOLATION");
            }

            return List.of();
        }
    }

    static class ArchitectureCatalog {
        private final Map<String, Architecture> architectures =
            new HashMap<>();

        public void register(Architecture architecture) {
            Objects.requireNonNull(architecture);

            if (architectures.putIfAbsent(
                architecture.id(),
                architecture
            ) != null) {
                throw new IllegalArgumentException(
                    "Duplicate architecture: " + architecture.id()
                );
            }
        }

        public Architecture get(String id) {
            Architecture architecture = architectures.get(id);

            if (architecture == null) {
                throw new IllegalArgumentException(
                    "Architecture not found: " + id
                );
            }

            return architecture;
        }

        public List<Architecture> all() {
            return List.copyOf(architectures.values());
        }

        public void validateDependencies() {
            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();

            for (String id : architectures.keySet()) {
                visit(id, visited, active);
            }
        }

        private void visit(
            String id,
            Set<String> visited,
            Set<String> active
        ) {
            if (active.contains(id)) {
                throw new IllegalStateException(
                    "Dependency cycle detected: " + id
                );
            }

            if (visited.contains(id)) {
                return;
            }

            Architecture architecture = get(id);
            active.add(id);

            for (String dependency : architecture.dependencies()) {
                if (!architectures.containsKey(dependency)) {
                    throw new IllegalStateException(
                        "Unknown dependency: " + dependency
                    );
                }

                visit(dependency, visited, active);
            }

            active.remove(id);
            visited.add(id);
        }
    }

    static class ReliabilityService {
        public double serialAvailability(List<Double> components) {
            double result = 1;

            for (double availability : components) {
                if (!Double.isFinite(availability) ||
                    availability <= 0 ||
                    availability > 1) {
                    throw new IllegalArgumentException(
                        "Invalid component availability"
                    );
                }

                result *= availability;
            }

            return result;
        }

        public double annualDowntimeHours(double availabilityPercent) {
            if (availabilityPercent <= 0 ||
                availabilityPercent > 100) {
                throw new IllegalArgumentException(
                    "Invalid availability"
                );
            }

            return 8760 * (1 - availabilityPercent / 100);
        }

        public double expectedAnnualLoss(List<Risk> risks) {
            return risks.stream()
                .mapToDouble(Risk::expectedAnnualLoss)
                .sum();
        }
    }

    static class ArchitectureEvaluationService {
        private final ArchitectureCatalog catalog;
        private final WorkloadProfile workload;
        private final GovernancePolicy policy;
        private final DecisionWeights weights;
        private final List<EvaluationRule> rules;
        private final ReliabilityService reliabilityService =
            new ReliabilityService();

        ArchitectureEvaluationService(
            ArchitectureCatalog catalog,
            WorkloadProfile workload,
            GovernancePolicy policy,
            DecisionWeights weights
        ) {
            this.catalog = Objects.requireNonNull(catalog);
            this.workload = Objects.requireNonNull(workload);
            this.policy = Objects.requireNonNull(policy);
            this.weights = Objects.requireNonNull(weights);

            this.rules = List.of(
                new BudgetRule(),
                new AvailabilityRule(),
                new CapacityRule(),
                new LatencyRule()
            );
        }

        private double calculateAvailability(Architecture architecture) {
            List<Double> componentAvailability = new ArrayList<>();

            componentAvailability.add(
                architecture.metrics().availabilityPercent() / 100
            );

            for (String dependency : architecture.dependencies()) {
                Architecture dependencyArchitecture = catalog.get(dependency);

                componentAvailability.add(
                    dependencyArchitecture.metrics().availabilityPercent() / 100
                );
            }

            return reliabilityService.serialAvailability(
                componentAvailability
            );
        }

        public ArchitectureEvaluation evaluate(Architecture architecture) {
            List<String> violations = rules.stream()
                .flatMap(rule ->
                    rule.evaluate(architecture, workload, policy).stream()
                )
                .toList();

            if (policy.requireDisasterRecovery() &&
                architecture.metrics().recoveryTimeMinutes() <= 0) {
                violations = new ArrayList<>(violations);
                violations.add("DISASTER_RECOVERY_NOT_DEFINED");
            }

            double monthlyCost = architecture.metrics().monthlyCost();
            double availability = calculateAvailability(architecture);

            double costScore =
                100 / (1 + monthlyCost / Math.max(policy.monthlyBudget(), 1));

            double latencyScore = Math.max(
                0,
                Math.min(
                    100,
                    100 * policy.maximumLatency() /
                    Math.max(
                        policy.maximumLatency(),
                        architecture.metrics().latencyMs()
                    )
                )
            );

            double throughputScore = Math.min(
                100,
                100 * architecture.metrics().throughputRps() /
                    Math.max(workload.peakRequestsPerSecond(), 1)
            );

            double performanceScore =
                (latencyScore + throughputScore) / 2;

            double reliabilityScore = availability * 100;

            double complexityScore =
                (11 - architecture.metrics().complexity()) * 10;

            double scalabilityScore =
                architecture.metrics().scalability() * 10;

            double weightedScore =
                costScore * weights.cost() +
                performanceScore * weights.performance() +
                reliabilityScore * weights.reliability() +
                complexityScore * weights.complexity() +
                scalabilityScore * weights.scalability();

            return new ArchitectureEvaluation(
                architecture.id(),
                architecture.name(),
                monthlyCost,
                monthlyCost * 12,
                availability * 100,
                reliabilityService.annualDowntimeHours(availability * 100),
                performanceScore,
                costScore,
                reliabilityScore,
                complexityScore,
                scalabilityScore,
                weightedScore,
                violations.isEmpty(),
                violations
            );
        }

        public List<ArchitectureEvaluation> evaluateAll() {
            catalog.validateDependencies();

            return catalog.all().stream()
                .map(this::evaluate)
                .sorted(
                    Comparator
                        .comparing(ArchitectureEvaluation::eligible)
                        .reversed()
                        .thenComparing(
                            ArchitectureEvaluation::weightedScore,
                            Comparator.reverseOrder()
                        )
                )
                .toList();
        }
    }

    static class ParetoService {
        public List<Architecture> calculateFrontier(
            List<Architecture> architectures
        ) {
            return architectures.stream()
                .filter(candidate ->
                    architectures.stream().noneMatch(other ->
                        !other.id().equals(candidate.id()) &&
                        dominates(other, candidate)
                    )
                )
                .toList();
        }

        private boolean dominates(Architecture a, Architecture b) {
            ArchitectureMetrics x = a.metrics();
            ArchitectureMetrics y = b.metrics();

            boolean noWorse =
                x.monthlyCost() <= y.monthlyCost() &&
                x.latencyMs() <= y.latencyMs() &&
                x.availabilityPercent() >= y.availabilityPercent() &&
                x.throughputRps() >= y.throughputRps();

            boolean strictlyBetter =
                x.monthlyCost() < y.monthlyCost() ||
                x.latencyMs() < y.latencyMs() ||
                x.availabilityPercent() > y.availabilityPercent() ||
                x.throughputRps() > y.throughputRps();

            return noWorse && strictlyBetter;
        }
    }

    static class DecisionAuditService {
        private final List<ArchitectureDecision> decisions =
            new ArrayList<>();

        public void record(ArchitectureDecision decision) {
            Objects.requireNonNull(decision);

            if (decision.title().isBlank() ||
                decision.context().isBlank()) {
                throw new IllegalArgumentException(
                    "Decision title and context are required"
                );
            }

            decisions.add(decision);
        }

        public List<ArchitectureDecision> history() {
            return List.copyOf(decisions);
        }
    }

    private static void requireNonNegative(
        String field,
        double value
    ) {
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException(
                field + " must be finite and non-negative"
            );
        }
    }

    private static void requireAtLeast(
        String field,
        double value,
        double minimum
    ) {
        if (!Double.isFinite(value) || value < minimum) {
            throw new IllegalArgumentException(
                field + " must be at least " + minimum
            );
        }
    }

    private static Architecture createArchitecture(
        String id,
        String name,
        ArchitectureType type,
        double infrastructure,
        double operations,
        double latency,
        double throughput,
        double availability,
        double complexity,
        double scalability,
        double recovery
    ) {
        return new Architecture(
            id,
            name,
            type,
            new ArchitectureMetrics(
                infrastructure,
                operations,
                latency,
                throughput,
                availability,
                complexity,
                scalability,
                recovery
            ),
            Set.of(),
            "Production"
        );
    }

    private static void runTests() {
        ReliabilityService service = new ReliabilityService();

        double availability = service.serialAvailability(
            List.of(0.99, 0.99)
        );

        if (Math.abs(availability - 0.9801) > 1e-9) {
            throw new IllegalStateException(
                "Reliability test failed"
            );
        }

        double downtime = service.annualDowntimeHours(99.9);

        if (Math.abs(downtime - 8.76) > 1e-9) {
            throw new IllegalStateException(
                "Downtime test failed"
            );
        }

        double risk = service.expectedAnnualLoss(
            List.of(
                new Risk(
                    "Database outage",
                    RiskCategory.RELIABILITY,
                    Severity.HIGH,
                    0.10,
                    50000
                )
            )
        );

        if (risk != 5000) {
            throw new IllegalStateException("Risk test failed");
        }
    }

    public static void main(String[] args) {
        try {
            runTests();

            ArchitectureCatalog catalog = new ArchitectureCatalog();

            catalog.register(createArchitecture(
                "modular",
                "Modular Monolith",
                ArchitectureType.MODULAR_MONOLITH,
                1200, 800, 95, 1800, 99.95, 3.5, 6.5, 20
            ));

            catalog.register(createArchitecture(
                "microservices",
                "Microservices",
                ArchitectureType.MICROSERVICES,
                4200, 3500, 125, 3500, 99.90, 8.5, 9.5, 35
            ));

            catalog.register(createArchitecture(
                "serverless",
                "Serverless",
                ArchitectureType.SERVERLESS,
                850, 1100, 160, 2200, 99.90, 5.5, 9.0, 15
            ));

            catalog.register(createArchitecture(
                "event-driven",
                "Event-Driven",
                ArchitectureType.EVENT_DRIVEN,
                2600, 2400, 140, 4200, 99.95, 7.5, 9.0, 25
            ));

            WorkloadProfile workload = new WorkloadProfile(
                "Commerce Peak Workload",
                1200,
                2,
                32,
                10000,
                200
            );

            GovernancePolicy policy = new GovernancePolicy(
                6000,
                99.9,
                1500,
                200,
                true
            );

            DecisionWeights weights = new DecisionWeights(
                0.25,
                0.20,
                0.25,
                0.15,
                0.15
            );

            ArchitectureEvaluationService evaluationService =
                new ArchitectureEvaluationService(
                    catalog,
                    workload,
                    policy,
                    weights
                );

            List<ArchitectureEvaluation> evaluations =
                evaluationService.evaluateAll();

            System.out.println("\nENTERPRISE ARCHITECTURE EVALUATION");
            System.out.println("=".repeat(110));

            for (ArchitectureEvaluation result : evaluations) {
                System.out.printf(
                    "%-26s Monthly: %9s Annual: %10s " +
                    "Availability: %8.4f%% Score: %7.2f Eligible: %s%n",
                    result.architectureName(),
                    BigDecimal.valueOf(result.monthlyCost())
                        .setScale(2, RoundingMode.HALF_UP),
                    BigDecimal.valueOf(result.annualCost())
                        .setScale(2, RoundingMode.HALF_UP),
                    result.availability(),
                    result.weightedScore(),
                    result.eligible()
                );

                result.violations().forEach(
                    violation -> System.out.println("  " + violation)
                );
            }

            System.out.println("\nWORKLOAD CHARACTERISTICS");
            System.out.printf(
                "Peak requests per second: %.2f%n",
                workload.peakRequestsPerSecond()
            );

            System.out.printf(
                "Estimated ingress: %.2f Mbps%n",
                workload.ingressMbps()
            );

            System.out.println("\nPARETO-OPTIMAL ARCHITECTURES");

            new ParetoService()
                .calculateFrontier(catalog.all())
                .forEach(a -> System.out.println("- " + a.name()));

            DecisionAuditService audit = new DecisionAuditService();

            audit.record(new ArchitectureDecision(
                UUID.randomUUID().toString(),
                "Commerce platform architecture selection",
                "Select an architecture using financial and technical constraints.",
                evaluations.stream()
                    .filter(ArchitectureEvaluation::eligible)
                    .findFirst()
                    .map(ArchitectureEvaluation::architectureId)
                    .orElse("none"),
                catalog.all().stream()
                    .map(Architecture::name)
                    .toList(),
                List.of(
                    "Weighted rankings are sensitive to business priorities.",
                    "Production selection requires workload benchmarking.",
                    "Reliability estimates depend on dependency topology."
                ),
                DecisionStatus.PROPOSED
            ));

            System.out.println(
                "\nRecorded architecture decisions: " +
                audit.history().size()
            );

            System.out.println("All Java 17 validation tests passed.");

        } catch (RuntimeException exception) {
            System.err.println(
                "Architecture evaluation failed: " +
                exception.getMessage()
            );
            System.exit(1);
        }
    }
}
