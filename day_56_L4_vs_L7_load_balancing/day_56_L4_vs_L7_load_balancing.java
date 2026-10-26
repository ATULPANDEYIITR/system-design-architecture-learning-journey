import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/*
 * L4 vs L7 Load Balancing
 *
 * Enterprise-oriented repository-independent model of:
 * - transport-flow load balancing
 * - HTTP-aware application routing
 * - health state
 * - session affinity
 * - route policies
 * - validation
 * - explicit failure handling
 *
 * Requires Java 17 or later.
 */

public class LoadBalancingEnterpriseModel {

    enum BackendState {
        HEALTHY,
        UNHEALTHY
    }

    enum RequestMethod {
        GET, POST, PUT, PATCH, DELETE
    }

    record BackendId(String value) {
        public BackendId {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Backend ID is required");
            }
        }
    }

    record BackendAddress(String host, int port) {
        public BackendAddress {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("Backend host is required");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("Invalid backend port");
            }
        }
    }

    static final class Backend {
        private final BackendId id;
        private final BackendAddress address;
        private final int weight;

        private BackendState state;
        private int activeConnections;
        private long requestsServed;

        Backend(
                BackendId id,
                BackendAddress address,
                int weight) {

            if (weight < 1) {
                throw new IllegalArgumentException("Weight must be positive");
            }

            this.id = Objects.requireNonNull(id);
            this.address = Objects.requireNonNull(address);
            this.weight = weight;
            this.state = BackendState.HEALTHY;
        }

        BackendId id() {
            return id;
        }

        BackendAddress address() {
            return address;
        }

        BackendState state() {
            return state;
        }

        int activeConnections() {
            return activeConnections;
        }

        long requestsServed() {
            return requestsServed;
        }

        boolean available() {
            return state == BackendState.HEALTHY && weight > 0;
        }

        void markUnhealthy() {
            state = BackendState.UNHEALTHY;
        }

        void markHealthy() {
            state = BackendState.HEALTHY;
        }

        void openConnection() {
            if (!available()) {
                throw new IllegalStateException(
                        "Cannot open connection to unavailable backend");
            }
            activeConnections++;
        }

        void closeConnection() {
            activeConnections = Math.max(0, activeConnections - 1);
        }

        void serveRequest() {
            if (!available()) {
                throw new IllegalStateException(
                        "Unavailable backend cannot serve request");
            }
            requestsServed++;
        }
    }

    record TcpFlow(
            String sourceIp,
            int sourcePort,
            String destinationIp,
            int destinationPort) {

        TcpFlow {
            if (sourceIp == null || sourceIp.isBlank()) {
                throw new IllegalArgumentException("Source IP required");
            }
            if (destinationIp == null || destinationIp.isBlank()) {
                throw new IllegalArgumentException("Destination IP required");
            }
            if (sourcePort < 1 || sourcePort > 65535 ||
                    destinationPort < 1 || destinationPort > 65535) {
                throw new IllegalArgumentException("Invalid TCP port");
            }
        }

        String key() {
            return sourceIp + ":" + sourcePort + "->" +
                    destinationIp + ":" + destinationPort;
        }
    }

    record HttpRequest(
            RequestMethod method,
            String host,
            String path,
            Map<String, String> headers) {

        HttpRequest {
            Objects.requireNonNull(method);

            if (host == null || host.isBlank() || host.length() > 253) {
                throw new IllegalArgumentException("Invalid HTTP host");
            }

            if (path == null || !path.startsWith("/") || path.length() > 4096) {
                throw new IllegalArgumentException("Invalid HTTP path");
            }

            headers = Map.copyOf(
                    headers == null ? Map.of() : headers);
        }

        Optional<String> sessionId() {
            String cookie = headers.getOrDefault("Cookie", "");

            for (String token : cookie.split(";")) {
                String trimmed = token.trim();

                if (trimmed.startsWith("SESSION_ID=")) {
                    String value = trimmed.substring("SESSION_ID=".length());

                    if (!value.isBlank() && value.length() <= 128) {
                        return Optional.of(value);
                    }
                }
            }

            return Optional.empty();
        }
    }

    static final class L4FlowBalancer {
        private final List<Backend> backends;
        private final Map<String, BackendId> flowTable = new HashMap<>();

        L4FlowBalancer(List<Backend> backends) {
            if (backends.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one L4 backend is required");
            }

            this.backends = new ArrayList<>(backends);
        }

        Backend find(BackendId id) {
            return backends.stream()
                    .filter(backend -> backend.id().equals(id))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                            "Unknown backend: " + id.value()));
        }

        Backend select(TcpFlow flow) {
            String key = flow.key();

            BackendId existingId = flowTable.get(key);

            if (existingId != null) {
                Backend existing = find(existingId);

                if (existing.available()) {
                    return existing;
                }

                flowTable.remove(key);
            }

            List<Backend> candidates = backends.stream()
                    .filter(Backend::available)
                    .toList();

            if (candidates.isEmpty()) {
                throw new IllegalStateException(
                        "No healthy L4 backend is available");
            }

            int index = Math.floorMod(
                    key.hashCode(),
                    candidates.size());

            Backend selected = candidates.get(index);
            selected.openConnection();
            flowTable.put(key, selected.id());

            return selected;
        }

        void close(TcpFlow flow) {
            BackendId id = flowTable.remove(flow.key());

            if (id != null) {
                find(id).closeConnection();
            }
        }

        List<Backend> backends() {
            return List.copyOf(backends);
        }
    }

    interface RoutePolicy {
        boolean matches(HttpRequest request);

        List<Backend> candidates(
                HttpRequest request,
                List<Backend> allBackends);
    }

    static final class PathRoutePolicy implements RoutePolicy {
        private final String prefix;
        private final List<BackendId> backendIds;

        PathRoutePolicy(
                String prefix,
                List<BackendId> backendIds) {

            if (!prefix.startsWith("/")) {
                throw new IllegalArgumentException(
                        "Route prefix must start with '/'");
            }

            this.prefix = prefix;
            this.backendIds = List.copyOf(backendIds);
        }

        @Override
        public boolean matches(HttpRequest request) {
            return request.path().startsWith(prefix);
        }

        @Override
        public List<Backend> candidates(
                HttpRequest request,
                List<Backend> allBackends) {

            return allBackends.stream()
                    .filter(backend -> backendIds.contains(backend.id()))
                    .filter(Backend::available)
                    .toList();
        }
    }

    static final class L7ApplicationBalancer {
        private final List<Backend> backends;
        private final List<RoutePolicy> policies = new ArrayList<>();
        private final Map<String, BackendId> sessionAffinity = new HashMap<>();

        L7ApplicationBalancer(List<Backend> backends) {
            if (backends.isEmpty()) {
                throw new IllegalArgumentException(
                        "At least one L7 backend is required");
            }

            this.backends = new ArrayList<>(backends);
        }

        void addPolicy(RoutePolicy policy) {
            policies.add(Objects.requireNonNull(policy));
        }

        Backend find(BackendId id) {
            return backends.stream()
                    .filter(backend -> backend.id().equals(id))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                            "Unknown backend: " + id.value()));
        }

        private List<Backend> routeCandidates(HttpRequest request) {
            for (RoutePolicy policy : policies) {
                if (policy.matches(request)) {
                    List<Backend> candidates =
                            policy.candidates(request, backends);

                    if (!candidates.isEmpty()) {
                        return candidates;
                    }

                    throw new IllegalStateException(
                            "Route matched but has no healthy backend");
                }
            }

            return backends.stream()
                    .filter(Backend::available)
                    .toList();
        }

        private Backend leastConnections(List<Backend> candidates) {
            return candidates.stream()
                    .min(Comparator.comparingInt(
                            Backend::activeConnections))
                    .orElseThrow(() -> new IllegalStateException(
                            "No healthy application backend"));
        }

        Backend route(HttpRequest request) {
            List<Backend> candidates = routeCandidates(request);

            if (candidates.isEmpty()) {
                throw new IllegalStateException(
                        "No healthy L7 backend is available");
            }

            Optional<String> session = request.sessionId();

            if (session.isPresent()) {
                BackendId existingId =
                        sessionAffinity.get(session.get());

                if (existingId != null) {
                    Backend existing = find(existingId);

                    boolean eligible = existing.available() &&
                            candidates.stream()
                                    .anyMatch(
                                            backend ->
                                                    backend.id().equals(
                                                            existing.id()));

                    if (eligible) {
                        existing.serveRequest();
                        return existing;
                    }
                }

                Backend selected = leastConnections(candidates);
                sessionAffinity.put(session.get(), selected.id());
                selected.serveRequest();
                return selected;
            }

            Backend selected = leastConnections(candidates);
            selected.serveRequest();
            return selected;
        }

        List<Backend> backends() {
            return List.copyOf(backends);
        }
    }

    private static void printState(
            String title,
            List<Backend> backends) {

        System.out.println("\n" + title);

        for (Backend backend : backends) {
            System.out.printf(
                    "%-10s state=%-10s connections=%d requests=%d%n",
                    backend.id().value(),
                    backend.state().name().toLowerCase(),
                    backend.activeConnections(),
                    backend.requestsServed());
        }
    }

    public static void main(String[] args) {
        List<Backend> l4Backends = List.of(
                new Backend(
                        new BackendId("api-1"),
                        new BackendAddress("10.0.0.11", 443),
                        1),
                new Backend(
                        new BackendId("api-2"),
                        new BackendAddress("10.0.0.12", 443),
                        1),
                new Backend(
                        new BackendId("api-3"),
                        new BackendAddress("10.0.0.13", 443),
                        1)
        );

        L4FlowBalancer l4 = new L4FlowBalancer(l4Backends);

        TcpFlow flow = new TcpFlow(
                "192.168.1.10",
                50001,
                "203.0.113.10",
                443);

        Backend initial = l4.select(flow);
        System.out.println("L4 selected: " + initial.id().value());

        initial.markUnhealthy();

        Backend remapped = l4.select(flow);
        System.out.println(
                "L4 selected after failure: " +
                        remapped.id().value());

        l4.close(flow);

        printState("L4 backend state", l4.backends());

        List<Backend> l7Backends = List.of(
                new Backend(
                        new BackendId("api-1"),
                        new BackendAddress("10.0.0.11", 8080),
                        1),
                new Backend(
                        new BackendId("api-2"),
                        new BackendAddress("10.0.0.12", 8080),
                        1),
                new Backend(
                        new BackendId("static-1"),
                        new BackendAddress("10.0.0.21", 8080),
                        1)
        );

        L7ApplicationBalancer l7 =
                new L7ApplicationBalancer(l7Backends);

        l7.addPolicy(
                new PathRoutePolicy(
                        "/api",
                        List.of(
                                new BackendId("api-1"),
                                new BackendId("api-2"))));

        l7.addPolicy(
                new PathRoutePolicy(
                        "/static",
                        List.of(new BackendId("static-1"))));

        HttpRequest apiRequest = new HttpRequest(
                RequestMethod.GET,
                "api.example.com",
                "/api/orders",
                Map.of(
                        "Cookie",
                        "SESSION_ID=customer-42"));

        HttpRequest staticRequest = new HttpRequest(
                RequestMethod.GET,
                "cdn.example.com",
                "/static/app.js",
                Map.of());

        Backend apiBackend = l7.route(apiRequest);
        Backend staticBackend = l7.route(staticRequest);

        System.out.println(
                "\nL7 API selected: " +
                        apiBackend.id().value());

        System.out.println(
                "L7 static selected: " +
                        staticBackend.id().value());

        // Session affinity is application state, so it must be invalidated
        // when the selected backend becomes unavailable.
        apiBackend.markUnhealthy();

        Backend failover = l7.route(
                new HttpRequest(
                        RequestMethod.GET,
                        "api.example.com",
                        "/api/orders",
                        Map.of(
                                "Cookie",
                                "SESSION_ID=customer-42")));

        System.out.println(
                "L7 session failover: " +
                        failover.id().value());

        try {
            new HttpRequest(
                    RequestMethod.GET,
                    "api.example.com",
                    "api/orders",
                    Map.of());
        } catch (IllegalArgumentException exception) {
            System.out.println(
                    "Validation failure: " +
                            exception.getMessage());
        }

        printState("L7 backend state", l7.backends());

        System.out.println("""
                
                Enterprise design boundary:
                L4 protects and distributes transport flows.
                L7 evaluates application requests and routing policies.
                L4 state is primarily connection-oriented.
                L7 state can include sessions, HTTP routing rules, and
                application health semantics.
                """);
    }
}
