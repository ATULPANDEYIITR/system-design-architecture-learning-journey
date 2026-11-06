import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Predicate;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class MicroservicesArchitecture {

    enum ServiceStatus {
        REGISTERED,
        DEPLOYING,
        HEALTHY,
        DEGRADED,
        UNAVAILABLE
    }

    enum DeploymentStatus {
        PENDING,
        SUCCESS,
        FAILED,
        ROLLED_BACK
    }

    enum DependencyType {
        SYNCHRONOUS,
        ASYNCHRONOUS
    }

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class DependencyException extends DomainException {
        DependencyException(String message) {
            super(message);
        }
    }

    static class CompatibilityException extends DomainException {
        CompatibilityException(String message) {
            super(message);
        }
    }

    static final Pattern NAME_PATTERN =
        Pattern.compile("[a-z][a-z0-9-]{1,48}");

    static final Pattern VERSION_PATTERN =
        Pattern.compile("\\d+\\.\\d+\\.\\d+");

    record ServiceContract(
        String serviceName,
        String version,
        int apiVersion,
        Set<String> endpoints,
        boolean backwardCompatible
    ) {
        ServiceContract {
            Objects.requireNonNull(serviceName);
            Objects.requireNonNull(version);
            Objects.requireNonNull(endpoints);

            if (!NAME_PATTERN.matcher(serviceName).matches()) {
                throw new DomainException("Invalid service name.");
            }

            if (!VERSION_PATTERN.matcher(version).matches()) {
                throw new DomainException("Invalid semantic version.");
            }

            if (apiVersion < 1 || endpoints.isEmpty()) {
                throw new DomainException("Invalid service contract.");
            }

            if (endpoints.stream().anyMatch(
                endpoint -> endpoint == null ||
                    !endpoint.startsWith("/")
            )) {
                throw new DomainException("Invalid endpoint.");
            }

            endpoints = Set.copyOf(endpoints);
        }
    }

    record Dependency(
        String targetService,
        DependencyType type,
        boolean required
    ) {
        Dependency {
            Objects.requireNonNull(targetService);
            Objects.requireNonNull(type);

            if (!NAME_PATTERN.matcher(targetService).matches()) {
                throw new DomainException("Invalid dependency name.");
            }
        }
    }

    static class Microservice {
        private final String name;
        private final String description;
        private final Set<Dependency> dependencies;
        private final AtomicInteger deploymentCount =
            new AtomicInteger();

        private volatile ServiceContract contract;
        private volatile ServiceStatus status;
        private final int instances;

        Microservice(
            String name,
            String description,
            ServiceContract contract,
            Set<Dependency> dependencies,
            int instances
        ) {
            if (!NAME_PATTERN.matcher(name).matches()) {
                throw new DomainException("Invalid service name.");
            }

            if (description == null || description.isBlank()) {
                throw new DomainException("Description is required.");
            }

            if (!contract.serviceName().equals(name)) {
                throw new DomainException("Contract identity mismatch.");
            }

            if (instances < 1) {
                throw new DomainException("Invalid instance count.");
            }

            this.name = name;
            this.description = description;
            this.contract = contract;
            this.dependencies = Set.copyOf(dependencies);
            this.instances = instances;
            this.status = ServiceStatus.REGISTERED;
        }

        String name() {
            return name;
        }

        ServiceContract contract() {
            return contract;
        }

        void setContract(ServiceContract contract) {
            this.contract = contract;
        }

        Set<Dependency> dependencies() {
            return dependencies;
        }

        ServiceStatus status() {
            return status;
        }

        void setStatus(ServiceStatus status) {
            this.status = status;
        }

        int deploymentCount() {
            return deploymentCount.get();
        }

        void incrementDeploymentCount() {
            deploymentCount.incrementAndGet();
        }

        int instances() {
            return instances;
        }
    }

    record DeploymentRecord(
        String deploymentId,
        String serviceName,
        String previousVersion,
        String targetVersion,
        DeploymentStatus status,
        Instant timestamp,
        String message
    ) {}

    record ServiceEvent(
        String eventId,
        String eventType,
        String sourceService,
        Map<String, String> payload,
        Instant timestamp
    ) {
        ServiceEvent {
            payload = Map.copyOf(payload);
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(eventType);
        }
    }

    interface HealthCheck {
        boolean isHealthy(
            Microservice service,
            ServiceContract candidate
        );
    }

    interface DeploymentPolicy {
        void validate(
            Microservice service,
            ServiceContract candidate
        );
    }

    static class BackwardCompatibilityPolicy
        implements DeploymentPolicy {

        @Override
        public void validate(
            Microservice service,
            ServiceContract candidate
        ) {
            ServiceContract current = service.contract();

            if (!candidate.serviceName().equals(service.name())) {
                throw new CompatibilityException(
                    "Service identity cannot change."
                );
            }

            int oldApi = current.apiVersion();
            int newApi = candidate.apiVersion();

            if (newApi < oldApi) {
                throw new CompatibilityException(
                    "API downgrade is prohibited."
                );
            }

            Set<String> removed =
                new HashSet<>(current.endpoints());

            removed.removeAll(candidate.endpoints());

            if (!removed.isEmpty() && newApi <= oldApi) {
                throw new CompatibilityException(
                    "Breaking endpoint removal requires an API version increase."
                );
            }

            if (!removed.isEmpty() && candidate.backwardCompatible()) {
                throw new CompatibilityException(
                    "Breaking contract marked compatible."
                );
            }
        }
    }

    static class ServiceRegistry {
        private final Map<String, Microservice> services =
            new ConcurrentHashMap<>();

        void register(Microservice service) {
            Microservice existing = services.putIfAbsent(
                service.name(), service
            );

            if (existing != null) {
                throw new DomainException(
                    "Service already registered: " + service.name()
                );
            }
        }

        Microservice get(String name) {
            Microservice service = services.get(name);

            if (service == null) {
                throw new DomainException(
                    "Service not found: " + name
                );
            }

            return service;
        }

        List<String> deploymentOrder() {
            Set<String> visited = new HashSet<>();
            Set<String> active = new HashSet<>();
            List<String> result = new ArrayList<>();

            services.keySet().stream()
                .sorted()
                .forEach(name ->
                    visit(name, visited, active, result)
                );

            return List.copyOf(result);
        }

        private void visit(
            String name,
            Set<String> visited,
            Set<String> active,
            List<String> result
        ) {
            if (active.contains(name)) {
                throw new DependencyException(
                    "Circular dependency: " + name
                );
            }

            if (visited.contains(name)) {
                return;
            }

            Microservice service = get(name);

            active.add(name);

            service.dependencies().stream()
                .sorted(Comparator.comparing(
                    Dependency::targetService
                ))
                .forEach(dependency -> {
                    if (!services.containsKey(
                        dependency.targetService()
                    )) {
                        if (dependency.required()) {
                            throw new DependencyException(
                                "Missing dependency: " +
                                dependency.targetService()
                            );
                        }
                    } else {
                        visit(
                            dependency.targetService(),
                            visited,
                            active,
                            result
                        );
                    }
                });

            active.remove(name);
            visited.add(name);
            result.add(name);
        }

        List<String> consumers(String provider) {
            get(provider);

            return services.values().stream()
                .filter(service ->
                    service.dependencies().stream().anyMatch(
                        dependency ->
                            dependency.targetService().equals(provider)
                    )
                )
                .map(Microservice::name)
                .sorted()
                .collect(Collectors.toList());
        }

        List<Microservice> inventory() {
            return services.values().stream()
                .sorted(Comparator.comparing(Microservice::name))
                .collect(Collectors.toList());
        }
    }

    static class DeploymentService {
        private final ServiceRegistry registry;
        private final DeploymentPolicy policy;
        private final HealthCheck healthCheck;

        private final List<DeploymentRecord> history =
            Collections.synchronizedList(new ArrayList<>());

        private final Map<String, ServiceContract> artifacts =
            new ConcurrentHashMap<>();

        DeploymentService(
            ServiceRegistry registry,
            DeploymentPolicy policy,
            HealthCheck healthCheck
        ) {
            this.registry = registry;
            this.policy = policy;
            this.healthCheck = healthCheck;
        }

        synchronized DeploymentRecord deploy(
            String name,
            ServiceContract candidate
        ) {
            Microservice service = registry.get(name);

            registry.deploymentOrder();
            policy.validate(service, candidate);

            ServiceContract previous = service.contract();

            String id = UUID.randomUUID().toString();

            service.setStatus(ServiceStatus.DEPLOYING);

            DeploymentStatus result;
            String message;

            try {
                if (!healthCheck.isHealthy(service, candidate)) {
                    throw new DomainException(
                        "Deployment health check failed."
                    );
                }

                service.setContract(candidate);
                service.setStatus(ServiceStatus.HEALTHY);
                service.incrementDeploymentCount();

                artifacts.put(
                    name + ":" + candidate.version(),
                    candidate
                );

                result = DeploymentStatus.SUCCESS;
                message = "Independent deployment succeeded.";

            } catch (RuntimeException error) {
                service.setContract(previous);
                service.setStatus(ServiceStatus.HEALTHY);

                result = DeploymentStatus.ROLLED_BACK;
                message = error.getMessage();
            }

            DeploymentRecord record = new DeploymentRecord(
                id,
                name,
                previous.version(),
                candidate.version(),
                result,
                Instant.now(),
                message
            );

            history.add(record);
            return record;
        }

        synchronized DeploymentRecord rollback(
            String name,
            String targetVersion
        ) {
            Microservice service = registry.get(name);

            boolean successful = history.stream().anyMatch(
                record ->
                    record.serviceName().equals(name) &&
                    record.targetVersion().equals(targetVersion) &&
                    record.status() == DeploymentStatus.SUCCESS
            );

            if (!successful) {
                throw new DomainException(
                    "Target deployment was not successful."
                );
            }

            ServiceContract target = artifacts.get(
                name + ":" + targetVersion
            );

            if (target == null) {
                throw new DomainException(
                    "Deployment artifact unavailable."
                );
            }

            ServiceContract previous = service.contract();

            service.setContract(target);
            service.setStatus(ServiceStatus.HEALTHY);

            DeploymentRecord record = new DeploymentRecord(
                UUID.randomUUID().toString(),
                name,
                previous.version(),
                target.version(),
                DeploymentStatus.ROLLED_BACK,
                Instant.now(),
                "Previous deployment artifact restored."
            );

            history.add(record);
            return record;
        }

        List<DeploymentRecord> history() {
            synchronized (history) {
                return List.copyOf(history);
            }
        }
    }

    static class EventDispatcher {
        private final Map<String, List<
            java.util.function.Consumer<ServiceEvent>
        >> handlers = new ConcurrentHashMap<>();

        private final Set<String> processed =
            ConcurrentHashMap.newKeySet();

        private final List<ServiceEvent> deadLetters =
            Collections.synchronizedList(new ArrayList<>());

        void subscribe(
            String eventType,
            java.util.function.Consumer<ServiceEvent> handler
        ) {
            handlers.computeIfAbsent(
                eventType,
                ignored -> Collections.synchronizedList(
                    new ArrayList<>()
                )
            ).add(handler);
        }

        void publish(ServiceEvent event) {
            List<java.util.function.Consumer<ServiceEvent>> consumers =
                handlers.getOrDefault(event.eventType(), List.of());

            for (var consumer : consumers) {
                // A production implementation uses a separate delivery
                // identifier for every consumer and durable event storage.
                if (processed.contains(event.eventId())) {
                    return;
                }

                try {
                    consumer.accept(event);
                    processed.add(event.eventId());

                } catch (RuntimeException error) {
                    deadLetters.add(event);
                    System.err.println(
                        "Event delivery failed: " + error.getMessage()
                    );
                }
            }
        }

        int deadLetterCount() {
            return deadLetters.size();
        }
    }

    static ServiceContract contract(
        String name,
        String version,
        int apiVersion,
        Set<String> endpoints,
        boolean compatible
    ) {
        return new ServiceContract(
            name,
            version,
            apiVersion,
            endpoints,
            compatible
        );
    }

    static Microservice service(
        String name,
        String description,
        Set<Dependency> dependencies
    ) {
        return new Microservice(
            name,
            description,
            contract(
                name,
                "1.0.0",
                1,
                Set.of("/health", "/api"),
                true
            ),
            dependencies,
            2
        );
    }

    public static void main(String[] args) {
        System.out.println("MICROSERVICES ENTERPRISE MODEL");
        System.out.println("=".repeat(55));

        ServiceRegistry registry = new ServiceRegistry();

        Microservice payment = service(
            "payment-service",
            "Payment processing",
            Set.of()
        );

        Microservice inventory = service(
            "inventory-service",
            "Inventory management",
            Set.of()
        );

        Microservice orders = service(
            "order-service",
            "Order lifecycle management",
            Set.of(
                new Dependency(
                    "payment-service",
                    DependencyType.SYNCHRONOUS,
                    true
                ),
                new Dependency(
                    "inventory-service",
                    DependencyType.ASYNCHRONOUS,
                    true
                )
            )
        );

        registry.register(payment);
        registry.register(inventory);
        registry.register(orders);

        System.out.println("\nDEPENDENCY ORDER");

        registry.deploymentOrder().forEach(
            System.out::println
        );

        System.out.println("\nSERVICE INVENTORY");

        for (Microservice service : registry.inventory()) {
            System.out.printf(
                "%-22s %-10s %-12s instances=%d dependencies=%d%n",
                service.name(),
                service.contract().version(),
                service.status(),
                service.instances(),
                service.dependencies().size()
            );
        }

        DeploymentService deploymentService =
            new DeploymentService(
                registry,
                new BackwardCompatibilityPolicy(),
                (service, candidate) ->
                    !candidate.version().equals("1.2.0")
            );

        System.out.println("\nINDEPENDENT DEPLOYMENT");

        ServiceContract paymentV11 = contract(
            "payment-service",
            "1.1.0",
            1,
            Set.of(
                "/health",
                "/api",
                "/api/payment-status"
            ),
            true
        );

        DeploymentRecord success =
            deploymentService.deploy(
                "payment-service",
                paymentV11
            );

        System.out.println(success);

        System.out.println("\nFAILED DEPLOYMENT");

        ServiceContract paymentV12 = contract(
            "payment-service",
            "1.2.0",
            1,
            Set.of(
                "/health",
                "/api",
                "/api/payment-status",
                "/api/refunds"
            ),
            true
        );

        System.out.println(
            deploymentService.deploy(
                "payment-service",
                paymentV12
            )
        );

        System.out.println("\nARTIFACT ROLLBACK");

        System.out.println(
            deploymentService.rollback(
                "payment-service",
                "1.0.0"
            )
        );

        System.out.println("\nCONTRACT VALIDATION");

        try {
            ServiceContract breaking = contract(
                "payment-service",
                "2.0.0",
                1,
                Set.of("/health"),
                true
            );

            new BackwardCompatibilityPolicy().validate(
                payment,
                breaking
            );

        } catch (CompatibilityException error) {
            System.out.println("Rejected: " + error.getMessage());
        }

        System.out.println("\nEVENT-DRIVEN COMMUNICATION");

        EventDispatcher dispatcher = new EventDispatcher();

        AtomicInteger inventoryEvents = new AtomicInteger();

        dispatcher.subscribe(
            "order.created",
            event -> {
                inventoryEvents.incrementAndGet();

                System.out.println(
                    "Inventory received order " +
                    event.payload().get("orderId")
                );
            }
        );

        ServiceEvent event = new ServiceEvent(
            UUID.randomUUID().toString(),
            "order.created",
            "order-service",
            Map.of("orderId", "ORD-4001"),
            Instant.now()
        );

        dispatcher.publish(event);
        dispatcher.publish(event);

        if (inventoryEvents.get() != 1) {
            throw new DomainException(
                "Idempotency test failed."
            );
        }

        System.out.println("\nCONSUMERS OF PAYMENT SERVICE");

        registry.consumers("payment-service")
            .forEach(System.out::println);

        System.out.println("\nDEPLOYMENT HISTORY");

        deploymentService.history().forEach(
            System.out::println
        );

        System.out.println("\nFINAL SERVICE INVENTORY");

        registry.inventory().forEach(service ->
            System.out.printf(
                "%s | %s | %s | deployments=%d%n",
                service.name(),
                service.contract().version(),
                service.status(),
                service.deploymentCount()
            )
        );

        System.out.println("\nDead-letter events: " +
            dispatcher.deadLetterCount()
        );
    }
}
