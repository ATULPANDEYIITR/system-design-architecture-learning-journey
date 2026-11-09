import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Enterprise Service Discovery and Governance System.
 *
 * Java 17 implementation.
 *
 * Includes:
 * - Immutable service descriptors
 * - Instance registration and deregistration
 * - Lease expiration
 * - Health policies
 * - Reviewable state transitions
 * - Version and region-aware discovery
 * - Approval-style registration policies
 * - Circuit-breaker protection
 * - Weighted endpoint selection
 * - Concurrent service catalog
 * - Graceful draining
 * - Audit events
 */

public class ServiceDiscoveryEnterprise {

    enum HealthStatus {
        UNKNOWN,
        HEALTHY,
        UNHEALTHY,
        DRAINING
    }

    enum RegistrationStatus {
        PENDING,
        ACTIVE,
        REJECTED,
        DEREGISTERED
    }

    enum Environment {
        DEVELOPMENT,
        STAGING,
        PRODUCTION
    }

    static class DiscoveryException extends RuntimeException {
        DiscoveryException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DiscoveryException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class ServiceUnavailableException extends DiscoveryException {
        ServiceUnavailableException(String message) {
            super(message);
        }
    }

    record ServiceDescriptor(
        String serviceName,
        String version,
        String owner,
        Environment environment,
        String region
    ) {
        ServiceDescriptor {
            Objects.requireNonNull(serviceName);
            Objects.requireNonNull(version);
            Objects.requireNonNull(owner);
            Objects.requireNonNull(environment);
            Objects.requireNonNull(region);

            if (serviceName.isBlank() ||
                version.isBlank() ||
                owner.isBlank() ||
                region.isBlank()) {

                throw new ValidationException(
                    "Service descriptor contains blank fields"
                );
            }
        }
    }

    record RegistrationRequest(
        ServiceDescriptor descriptor,
        String instanceId,
        String host,
        int port,
        int weight,
        Duration lease,
        Map<String, String> metadata
    ) {
        RegistrationRequest {
            Objects.requireNonNull(descriptor);
            Objects.requireNonNull(instanceId);
            Objects.requireNonNull(host);
            Objects.requireNonNull(lease);
            Objects.requireNonNull(metadata);

            if (instanceId.isBlank() || host.isBlank()) {
                throw new ValidationException(
                    "Instance ID and host are required"
                );
            }

            if (port < 1 || port > 65535) {
                throw new ValidationException("Invalid port");
            }

            if (weight < 1 || weight > 1000) {
                throw new ValidationException("Invalid weight");
            }

            if (lease.isZero() || lease.isNegative()) {
                throw new ValidationException("Invalid lease");
            }

            metadata = Map.copyOf(metadata);
        }
    }

    static final class ServiceInstance {

        private final RegistrationRequest request;
        private final Instant registeredAt;

        private volatile Instant lastHeartbeat;
        private volatile HealthStatus health;
        private volatile int failures;
        private volatile int successes;

        ServiceInstance(RegistrationRequest request) {
            this.request = request;
            this.registeredAt = Instant.now();
            this.lastHeartbeat = registeredAt;
            this.health = HealthStatus.UNKNOWN;
        }

        String id() {
            return request.instanceId();
        }

        String serviceName() {
            return request.descriptor().serviceName();
        }

        String endpoint() {
            return request.host() + ":" + request.port();
        }

        String version() {
            return request.descriptor().version();
        }

        String region() {
            return request.descriptor().region();
        }

        int weight() {
            return request.weight();
        }

        Duration lease() {
            return request.lease();
        }

        Map<String, String> metadata() {
            return request.metadata();
        }

        HealthStatus health() {
            return health;
        }

        synchronized void heartbeat() {
            lastHeartbeat = Instant.now();
        }

        boolean expired(Instant now) {
            return Duration.between(lastHeartbeat, now)
                .compareTo(request.lease()) > 0;
        }

        synchronized HealthStatus updateHealth(
            boolean healthy,
            HealthPolicy policy
        ) {

            if (health == HealthStatus.DRAINING) {
                return health;
            }

            if (healthy) {
                failures = 0;
                successes++;

                if (successes >= policy.recoveryThreshold()) {
                    health = HealthStatus.HEALTHY;
                }
            } else {
                successes = 0;
                failures++;

                if (failures >= policy.failureThreshold()) {
                    health = HealthStatus.UNHEALTHY;
                }
            }

            return health;
        }

        synchronized void drain() {
            health = HealthStatus.DRAINING;
        }
    }

    record HealthPolicy(
        int failureThreshold,
        int recoveryThreshold
    ) {
        HealthPolicy {
            if (failureThreshold < 1 || recoveryThreshold < 1) {
                throw new ValidationException(
                    "Health thresholds must be positive"
                );
            }
        }
    }

    record DiscoveryPolicy(
        String serviceName,
        Optional<String> version,
        Optional<String> region,
        Map<String, String> metadata,
        boolean productionOnly
    ) {
        DiscoveryPolicy {
            Objects.requireNonNull(serviceName);
            Objects.requireNonNull(version);
            Objects.requireNonNull(region);
            metadata = Map.copyOf(metadata);

            if (serviceName.isBlank()) {
                throw new ValidationException("Service name is required");
            }
        }
    }

    interface RegistrationPolicy {
        void validate(RegistrationRequest request);
    }

    static final class ProductionRegistrationPolicy
        implements RegistrationPolicy {

        private final Set<String> authorizedOwners;

        ProductionRegistrationPolicy(Set<String> authorizedOwners) {
            this.authorizedOwners = Set.copyOf(authorizedOwners);
        }

        @Override
        public void validate(RegistrationRequest request) {
            ServiceDescriptor descriptor = request.descriptor();

            if (descriptor.environment() == Environment.PRODUCTION &&
                !authorizedOwners.contains(descriptor.owner())) {

                throw new ValidationException(
                    "Owner is not authorized for production registration"
                );
            }

            if (descriptor.environment() == Environment.PRODUCTION &&
                !request.metadata().containsKey("deploymentId")) {

                throw new ValidationException(
                    "Production registration requires deploymentId metadata"
                );
            }
        }
    }

    static final class CircuitBreaker {

        private final int threshold;
        private final Duration resetDuration;

        private int failures;
        private Instant openedAt;

        CircuitBreaker(int threshold, Duration resetDuration) {
            if (threshold < 1 || resetDuration.isNegative()) {
                throw new ValidationException(
                    "Invalid circuit breaker configuration"
                );
            }

            this.threshold = threshold;
            this.resetDuration = resetDuration;
        }

        synchronized boolean allowRequest() {
            if (openedAt == null) {
                return true;
            }

            return Duration.between(openedAt, Instant.now())
                .compareTo(resetDuration) >= 0;
        }

        synchronized void success() {
            failures = 0;
            openedAt = null;
        }

        synchronized void failure() {
            failures++;

            if (failures >= threshold) {
                openedAt = Instant.now();
            }
        }

        synchronized String state() {
            if (openedAt == null) return "CLOSED";

            if (allowRequest()) return "HALF_OPEN";

            return "OPEN";
        }
    }

    static final class ServiceCatalog {

        private final Map<String, ServiceInstance> instances =
            new ConcurrentHashMap<>();

        private final Map<String, Set<String>> serviceIndex =
            new ConcurrentHashMap<>();

        private final Map<String, CircuitBreaker> breakers =
            new ConcurrentHashMap<>();

        private final Map<String, AtomicInteger> selectionCounters =
            new ConcurrentHashMap<>();

        private final CopyOnWriteArrayList<String> auditEvents =
            new CopyOnWriteArrayList<>();

        private final HealthPolicy healthPolicy;
        private final RegistrationPolicy registrationPolicy;

        ServiceCatalog(
            HealthPolicy healthPolicy,
            RegistrationPolicy registrationPolicy
        ) {
            this.healthPolicy = healthPolicy;
            this.registrationPolicy = registrationPolicy;
        }

        void register(RegistrationRequest request) {
            registrationPolicy.validate(request);

            ServiceInstance instance = new ServiceInstance(request);

            ServiceInstance existing = instances.putIfAbsent(
                instance.id(),
                instance
            );

            if (existing != null) {
                throw new ValidationException(
                    "Duplicate instance identifier"
                );
            }

            serviceIndex.computeIfAbsent(
                instance.serviceName(),
                ignored -> ConcurrentHashMap.newKeySet()
            ).add(instance.id());

            breakers.put(
                instance.id(),
                new CircuitBreaker(3, Duration.ofSeconds(5))
            );

            auditEvents.add(
                "REGISTERED " + instance.id() + " " + Instant.now()
            );
        }

        boolean deregister(String id) {
            ServiceInstance instance = instances.remove(id);

            if (instance == null) {
                return false;
            }

            Set<String> ids = serviceIndex.get(instance.serviceName());

            if (ids != null) {
                ids.remove(id);

                if (ids.isEmpty()) {
                    serviceIndex.remove(instance.serviceName(), ids);
                }
            }

            breakers.remove(id);

            auditEvents.add(
                "DEREGISTERED " + id + " " + Instant.now()
            );

            return true;
        }

        void heartbeat(String id) {
            ServiceInstance instance = requireInstance(id);

            instance.heartbeat();
        }

        HealthStatus updateHealth(String id, boolean healthy) {
            ServiceInstance instance = requireInstance(id);

            HealthStatus result = instance.updateHealth(
                healthy,
                healthPolicy
            );

            auditEvents.add(
                "HEALTH " + id + " " + result
            );

            return result;
        }

        void drain(String id) {
            ServiceInstance instance = requireInstance(id);

            instance.drain();

            auditEvents.add("DRAINING " + id);
        }

        private ServiceInstance requireInstance(String id) {
            ServiceInstance instance = instances.get(id);

            if (instance == null) {
                throw new DiscoveryException("Unknown instance: " + id);
            }

            return instance;
        }

        List<ServiceInstance> discover(DiscoveryPolicy policy) {
            Set<String> ids = serviceIndex.getOrDefault(
                policy.serviceName(),
                Collections.emptySet()
            );

            Instant now = Instant.now();

            return ids.stream()
                .map(instances::get)
                .filter(Objects::nonNull)
                .filter(instance ->
                    instance.health() == HealthStatus.HEALTHY
                )
                .filter(instance -> !instance.expired(now))
                .filter(instance ->
                    policy.version().isEmpty() ||
                    policy.version().get().equals(instance.version())
                )
                .filter(instance ->
                    policy.region().isEmpty() ||
                    policy.region().get().equals(instance.region())
                )
                .filter(instance ->
                    policy.metadata().entrySet().stream().allMatch(entry ->
                        entry.getValue().equals(
                            instance.metadata().get(entry.getKey())
                        )
                    )
                )
                .sorted(Comparator.comparing(ServiceInstance::id))
                .collect(Collectors.toList());
        }

        ServiceInstance selectRoundRobin(DiscoveryPolicy policy) {
            List<ServiceInstance> available = discover(policy);

            if (available.isEmpty()) {
                throw new ServiceUnavailableException(
                    "No healthy instance found"
                );
            }

            AtomicInteger counter = selectionCounters.computeIfAbsent(
                policy.serviceName(),
                ignored -> new AtomicInteger()
            );

            int index = Math.floorMod(
                counter.getAndIncrement(),
                available.size()
            );

            return available.get(index);
        }

        ServiceInstance selectWeighted(DiscoveryPolicy policy) {
            List<ServiceInstance> available = discover(policy)
                .stream()
                .filter(instance -> breakers.get(instance.id()).allowRequest())
                .toList();

            if (available.isEmpty()) {
                throw new ServiceUnavailableException(
                    "No endpoint passed circuit-breaker policy"
                );
            }

            int totalWeight = available.stream()
                .mapToInt(ServiceInstance::weight)
                .sum();

            int choice = java.util.concurrent.ThreadLocalRandom.current()
                .nextInt(totalWeight);

            for (ServiceInstance instance : available) {
                choice -= instance.weight();

                if (choice < 0) {
                    return instance;
                }
            }

            throw new IllegalStateException("Weighted selection failed");
        }

        void recordRequest(String id, boolean successful) {
            CircuitBreaker breaker = breakers.get(id);

            if (breaker == null) {
                throw new DiscoveryException("Unknown instance");
            }

            if (successful) {
                breaker.success();
            } else {
                breaker.failure();
            }

            auditEvents.add(
                "REQUEST " + id + " " + successful +
                " CIRCUIT=" + breaker.state()
            );
        }

        List<String> expireInstances() {
            Instant now = Instant.now();

            List<String> expired = instances.values()
                .stream()
                .filter(instance -> instance.expired(now))
                .map(ServiceInstance::id)
                .toList();

            expired.forEach(this::deregister);

            return expired;
        }

        List<ServiceInstance> list() {
            return instances.values().stream()
                .sorted(Comparator.comparing(ServiceInstance::id))
                .toList();
        }

        List<String> auditLog() {
            return List.copyOf(auditEvents);
        }
    }

    private static RegistrationRequest request(
        String service,
        String id,
        String host,
        int port,
        String version,
        Environment environment,
        String owner,
        String region,
        int weight
    ) {

        ServiceDescriptor descriptor = new ServiceDescriptor(
            service,
            version,
            owner,
            environment,
            region
        );

        Map<String, String> metadata = Map.of(
            "deploymentId", "deploy-" + id,
            "environment", environment.name().toLowerCase()
        );

        return new RegistrationRequest(
            descriptor,
            id,
            host,
            port,
            weight,
            Duration.ofSeconds(60),
            metadata
        );
    }

    public static void main(String[] args) {
        try {
            RegistrationPolicy registrationPolicy =
                new ProductionRegistrationPolicy(
                    Set.of("payments-team", "inventory-team")
                );

            ServiceCatalog catalog = new ServiceCatalog(
                new HealthPolicy(2, 2),
                registrationPolicy
            );

            List<RegistrationRequest> deployment = List.of(
                request(
                    "payment-service",
                    "pay-001",
                    "10.0.1.10",
                    8001,
                    "2.1.0",
                    Environment.PRODUCTION,
                    "payments-team",
                    "ap-south-1",
                    3
                ),
                request(
                    "payment-service",
                    "pay-002",
                    "10.0.1.11",
                    8001,
                    "2.1.0",
                    Environment.PRODUCTION,
                    "payments-team",
                    "ap-south-1",
                    1
                ),
                request(
                    "inventory-service",
                    "inv-001",
                    "10.0.2.10",
                    8002,
                    "1.4.0",
                    Environment.PRODUCTION,
                    "inventory-team",
                    "ap-south-1",
                    2
                )
            );

            for (RegistrationRequest registration : deployment) {
                catalog.register(registration);

                catalog.updateHealth(
                    registration.instanceId(),
                    true
                );

                catalog.updateHealth(
                    registration.instanceId(),
                    true
                );
            }

            DiscoveryPolicy paymentPolicy = new DiscoveryPolicy(
                "payment-service",
                Optional.of("2.1.0"),
                Optional.of("ap-south-1"),
                Map.of("environment", "production"),
                true
            );

            System.out.println("DISCOVERED ENDPOINTS");

            for (ServiceInstance instance :
                 catalog.discover(paymentPolicy)) {

                System.out.println(
                    instance.id() + " " +
                    instance.endpoint() + " " +
                    instance.health()
                );
            }

            System.out.println("\nROUND-ROBIN");

            for (int i = 0; i < 4; i++) {
                System.out.println(
                    catalog.selectRoundRobin(paymentPolicy).endpoint()
                );
            }

            System.out.println("\nWEIGHTED ROUTING");

            for (int i = 0; i < 5; i++) {
                System.out.println(
                    catalog.selectWeighted(paymentPolicy).endpoint()
                );
            }

            System.out.println("\nFAILURE TRANSITION");

            catalog.updateHealth("pay-001", false);
            catalog.updateHealth("pay-001", false);

            System.out.println(
                "Healthy endpoints: " +
                catalog.discover(paymentPolicy).size()
            );

            System.out.println("\nCIRCUIT BREAKER");

            catalog.recordRequest("pay-002", false);
            catalog.recordRequest("pay-002", false);
            catalog.recordRequest("pay-002", false);

            System.out.println(
                catalog.selectWeighted(paymentPolicy).endpoint()
            );

            System.out.println("\nGRACEFUL DRAINING");

            catalog.drain("pay-002");

            System.out.println(
                "Available endpoints: " +
                catalog.discover(paymentPolicy).size()
            );

            System.out.println("\nDEREGISTRATION");

            catalog.deregister("inv-001");

            System.out.println(
                "Remaining instances: " + catalog.list().size()
            );

            System.out.println("\nAUDIT EVENTS");

            catalog.auditLog().forEach(System.out::println);

            System.out.println("\nVALIDATION TEST");

            try {
                RegistrationRequest unauthorized = request(
                    "payment-service",
                    "bad-001",
                    "10.0.1.20",
                    8001,
                    "2.1.0",
                    Environment.PRODUCTION,
                    "external-team",
                    "ap-south-1",
                    1
                );

                catalog.register(unauthorized);

            } catch (ValidationException error) {
                System.out.println(
                    "Registration rejected: " + error.getMessage()
                );
            }

        } catch (DiscoveryException error) {
            System.err.println(
                "Discovery operation failed: " + error.getMessage()
            );

            System.exitCode = 1;
        }
    }
}
