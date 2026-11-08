import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Enterprise API Gateway
 *
 * Java 17 implementation covering:
 * - HTTP routing
 * - Bearer-token authentication
 * - Scope-based authorization
 * - Token-bucket rate limiting
 * - Asynchronous service boundaries
 * - Upstream health and circuit breaking
 * - Gateway policy evaluation
 * - Request auditing
 * - Structured error handling
 *
 * Dependencies: Java 17 standard library.
 */

public class APIGateway {

    // ---------------------------------------------------
    // Domain enums
    // ---------------------------------------------------

    enum HttpMethod {
        GET, POST, PUT, PATCH, DELETE
    }

    enum ClientStatus {
        ACTIVE, DISABLED
    }

    enum CircuitState {
        CLOSED, OPEN, HALF_OPEN
    }

    // ---------------------------------------------------
    // Domain exceptions
    // ---------------------------------------------------

    static class GatewayException extends RuntimeException {

        private final int statusCode;
        private final String errorCode;

        GatewayException(
                int statusCode,
                String errorCode,
                String message
        ) {
            super(message);
            this.statusCode = statusCode;
            this.errorCode = errorCode;
        }

        int getStatusCode() {
            return statusCode;
        }

        String getErrorCode() {
            return errorCode;
        }
    }

    // ---------------------------------------------------
    // Immutable request and response records
    // ---------------------------------------------------

    record GatewayRequest(
            HttpMethod method,
            String path,
            Map<String, String> headers,
            Map<String, Object> body,
            String requestId
    ) {
        GatewayRequest {
            if (method == null || path == null ||
                    !path.startsWith("/") ||
                    path.length() > 2048 ||
                    path.contains("..")) {
                throw new GatewayException(
                        400,
                        "INVALID_REQUEST",
                        "Invalid request"
                );
            }

            headers = Map.copyOf(headers);
            body = Map.copyOf(body);

            if (requestId == null || requestId.isBlank()) {
                requestId = UUID.randomUUID().toString();
            }
        }
    }

    record GatewayResponse(
            int statusCode,
            Map<String, Object> body,
            Map<String, String> headers
    ) {
        GatewayResponse {
            body = Map.copyOf(body);
            headers = Map.copyOf(headers);
        }

        static GatewayResponse of(int status, String message) {
            return new GatewayResponse(
                    status,
                    Map.of("message", message),
                    Map.of()
            );
        }
    }

    // ---------------------------------------------------
    // Client identity and permissions
    // ---------------------------------------------------

    record ApiClient(
            String clientId,
            String token,
            Set<String> scopes,
            ClientStatus status
    ) {
        ApiClient {
            if (clientId == null || clientId.isBlank() ||
                    token == null || token.isBlank()) {
                throw new IllegalArgumentException(
                        "Client identity and token are required"
                );
            }

            scopes = Set.copyOf(scopes);
        }
    }

    static class ClientRegistry {

        private final Map<String, ApiClient> clients =
                new ConcurrentHashMap<>();

        void register(ApiClient client) {

            if (clients.putIfAbsent(
                    client.token(),
                    client
            ) != null) {
                throw new IllegalArgumentException(
                        "Duplicate API token"
                );
            }
        }

        ApiClient authenticate(GatewayRequest request) {

            String authorization = request.headers()
                    .getOrDefault("Authorization", "");

            if (!authorization.startsWith("Bearer ")) {
                throw new GatewayException(
                        401,
                        "UNAUTHENTICATED",
                        "Bearer token required"
                );
            }

            String token = authorization.substring(7).trim();

            ApiClient client = clients.get(token);

            if (client == null ||
                    client.status() != ClientStatus.ACTIVE) {
                throw new GatewayException(
                        401,
                        "INVALID_TOKEN",
                        "Invalid or disabled credentials"
                );
            }

            return client;
        }

        void authorize(ApiClient client, String scope) {

            if (!client.scopes().contains(scope)) {
                throw new GatewayException(
                        403,
                        "FORBIDDEN",
                        "Required scope not granted"
                );
            }
        }
    }

    // ---------------------------------------------------
    // Route policy
    // ---------------------------------------------------

    record RouteDefinition(
            String routeId,
            HttpMethod method,
            String pathPattern,
            String upstream,
            String requiredScope,
            int requestsPerSecond,
            int burstCapacity
    ) {
        RouteDefinition {
            if (routeId == null || routeId.isBlank() ||
                    pathPattern == null ||
                    !pathPattern.startsWith("/") ||
                    upstream == null ||
                    requiredScope == null ||
                    requestsPerSecond <= 0 ||
                    burstCapacity <= 0) {
                throw new IllegalArgumentException(
                        "Invalid route configuration"
                );
            }
        }
    }

    record RouteMatch(
            RouteDefinition route,
            Map<String, String> parameters
    ) {}

    // ---------------------------------------------------
    // Router
    // ---------------------------------------------------

    static class Router {

        private static class CompiledRoute {
            final RouteDefinition definition;
            final Pattern pattern;
            final List<String> parameterNames;
            final int specificity;

            CompiledRoute(RouteDefinition definition) {

                this.definition = definition;

                Matcher matcher = Pattern
                        .compile("\\{([a-zA-Z_][a-zA-Z0-9_]*)\\}")
                        .matcher(definition.pathPattern());

                StringBuffer regex = new StringBuffer();
                List<String> names = new ArrayList<>();

                while (matcher.find()) {
                    names.add(matcher.group(1));
                    matcher.appendReplacement(
                            regex,
                            "([^/]+)"
                    );
                }

                matcher.appendTail(regex);

                String expression = regex.toString()
                        .replace("/", "\\/");

                this.pattern = Pattern.compile(
                        "^" + expression + "$"
                );

                this.parameterNames = List.copyOf(names);

                this.specificity =
                        definition.pathPattern().split("/").length * 100
                        + definition.pathPattern()
                            .replaceAll("\\{[^}]+\\}", "")
                            .length();
            }
        }

        private final List<CompiledRoute> routes =
                new ArrayList<>();

        void register(RouteDefinition definition) {

            boolean duplicate = routes.stream().anyMatch(route ->
                    route.definition.routeId()
                            .equals(definition.routeId()) ||
                    (route.definition.method() == definition.method()
                    && route.definition.pathPattern()
                            .equals(definition.pathPattern()))
            );

            if (duplicate) {
                throw new IllegalArgumentException(
                        "Duplicate route"
                );
            }

            routes.add(new CompiledRoute(definition));

            routes.sort(
                    (a, b) -> Integer.compare(
                            b.specificity,
                            a.specificity
                    )
            );
        }

        RouteMatch resolve(HttpMethod method, String path) {

            for (CompiledRoute route : routes) {

                if (route.definition.method() != method) {
                    continue;
                }

                Matcher matcher = route.pattern.matcher(path);

                if (!matcher.matches()) {
                    continue;
                }

                Map<String, String> parameters =
                        new LinkedHashMap<>();

                for (int i = 0;
                     i < route.parameterNames.size();
                     i++) {

                    parameters.put(
                            route.parameterNames.get(i),
                            matcher.group(i + 1)
                    );
                }

                return new RouteMatch(
                        route.definition,
                        Collections.unmodifiableMap(parameters)
                );
            }

            return null;
        }
    }

    // ---------------------------------------------------
    // Thread-safe token bucket
    // ---------------------------------------------------

    static class TokenBucket {

        private final double refillRate;
        private final double capacity;

        private double tokens;
        private long lastRefill;

        TokenBucket(int rate, int capacity) {

            if (rate <= 0 || capacity <= 0) {
                throw new IllegalArgumentException(
                        "Rate and capacity must be positive"
                );
            }

            this.refillRate = rate;
            this.capacity = capacity;
            this.tokens = capacity;
            this.lastRefill = System.nanoTime();
        }

        synchronized boolean consume() {

            long now = System.nanoTime();

            double elapsed =
                    Math.max(0, now - lastRefill) / 1_000_000_000.0;

            tokens = Math.min(
                    capacity,
                    tokens + elapsed * refillRate
            );

            lastRefill = Math.max(lastRefill, now);

            if (tokens < 1.0) {
                return false;
            }

            tokens -= 1.0;
            return true;
        }

        synchronized int remaining() {
            return (int) tokens;
        }
    }

    static class RateLimiter {

        private final ConcurrentHashMap<String, TokenBucket>
                buckets = new ConcurrentHashMap<>();

        boolean allow(ApiClient client, RouteDefinition route) {

            String key = client.clientId() + ":" + route.routeId();

            TokenBucket bucket = buckets.computeIfAbsent(
                    key,
                    ignored -> new TokenBucket(
                            route.requestsPerSecond(),
                            route.burstCapacity()
                    )
            );

            return bucket.consume();
        }

        int remaining(ApiClient client, RouteDefinition route) {

            String key = client.clientId() + ":" + route.routeId();

            TokenBucket bucket = buckets.get(key);

            return bucket == null
                    ? route.burstCapacity()
                    : bucket.remaining();
        }
    }

    // ---------------------------------------------------
    // Upstream service contract
    // ---------------------------------------------------

    interface UpstreamService {

        GatewayResponse execute(
                GatewayRequest request,
                Map<String, String> parameters
        );
    }

    static class UserService implements UpstreamService {

        @Override
        public GatewayResponse execute(
                GatewayRequest request,
                Map<String, String> parameters
        ) {

            String userId = parameters.get("userId");

            return new GatewayResponse(
                    200,
                    Map.of(
                            "service", "user-service",
                            "userId", userId,
                            "name", "Example User"
                    ),
                    Map.of()
            );
        }
    }

    static class OrderService implements UpstreamService {

        @Override
        public GatewayResponse execute(
                GatewayRequest request,
                Map<String, String> parameters
        ) {

            Object amount = request.body().get("amount");

            if (!(amount instanceof Number number) ||
                    !Double.isFinite(number.doubleValue()) ||
                    number.doubleValue() <= 0) {
                return GatewayResponse.of(
                        400,
                        "A positive order amount is required"
                );
            }

            return new GatewayResponse(
                    201,
                    Map.of(
                            "orderId", UUID.randomUUID().toString(),
                            "amount", number,
                            "status", "CREATED"
                    ),
                    Map.of()
            );
        }
    }

    // ---------------------------------------------------
    // Circuit breaker
    // ---------------------------------------------------

    static class CircuitBreaker {

        private final int failureThreshold;
        private final long resetTimeoutMillis;

        private int failures;
        private long openedAt;
        private CircuitState state = CircuitState.CLOSED;

        CircuitBreaker(int threshold, long resetTimeoutMillis) {
            if (threshold <= 0 || resetTimeoutMillis <= 0) {
                throw new IllegalArgumentException(
                        "Invalid circuit breaker settings"
                );
            }

            this.failureThreshold = threshold;
            this.resetTimeoutMillis = resetTimeoutMillis;
        }

        synchronized boolean canExecute() {

            if (state == CircuitState.OPEN) {

                if (System.currentTimeMillis() - openedAt
                        >= resetTimeoutMillis) {
                    state = CircuitState.HALF_OPEN;
                    return true;
                }

                return false;
            }

            return true;
        }

        synchronized void success() {
            failures = 0;
            state = CircuitState.CLOSED;
        }

        synchronized void failure() {

            failures++;

            if (state == CircuitState.HALF_OPEN ||
                    failures >= failureThreshold) {
                state = CircuitState.OPEN;
                openedAt = System.currentTimeMillis();
            }
        }
    }

    // ---------------------------------------------------
    // Upstream registry
    // ---------------------------------------------------

    static class UpstreamRegistry {

        private final Map<String, UpstreamService> services =
                new ConcurrentHashMap<>();

        private final Map<String, CircuitBreaker> breakers =
                new ConcurrentHashMap<>();

        void register(
                String name,
                UpstreamService service
        ) {
            if (services.putIfAbsent(name, service) != null) {
                throw new IllegalArgumentException(
                        "Duplicate upstream service"
                );
            }

            breakers.put(
                    name,
                    new CircuitBreaker(3, 5000)
            );
        }

        GatewayResponse forward(
                String name,
                GatewayRequest request,
                Map<String, String> parameters
        ) {

            UpstreamService service = services.get(name);
            CircuitBreaker breaker = breakers.get(name);

            if (service == null || breaker == null) {
                throw new GatewayException(
                        502,
                        "UPSTREAM_NOT_FOUND",
                        "Upstream service unavailable"
                );
            }

            if (!breaker.canExecute()) {
                throw new GatewayException(
                        503,
                        "CIRCUIT_OPEN",
                        "Upstream circuit breaker is open"
                );
            }

            try {
                GatewayResponse response = service.execute(
                        request,
                        parameters
                );

                if (response.statusCode() >= 500) {
                    breaker.failure();
                } else {
                    breaker.success();
                }

                return response;

            } catch (RuntimeException exception) {
                breaker.failure();
                throw exception;
            }
        }
    }

    // ---------------------------------------------------
    // Audit records
    // ---------------------------------------------------

    record AuditRecord(
            String requestId,
            String clientId,
            String method,
            String path,
            int statusCode,
            Instant timestamp
    ) {}

    static class AuditService {

        private final List<AuditRecord> records =
                Collections.synchronizedList(new ArrayList<>());

        void record(
                GatewayRequest request,
                String clientId,
                int statusCode
        ) {
            records.add(new AuditRecord(
                    request.requestId(),
                    clientId,
                    request.method().name(),
                    request.path(),
                    statusCode,
                    Instant.now()
            ));
        }

        Map<Integer, Long> report() {

            synchronized (records) {
                Map<Integer, Long> counts = new HashMap<>();

                records.forEach(record ->
                        counts.merge(
                                record.statusCode(),
                                1L,
                                Long::sum
                        )
                );

                return Map.copyOf(counts);
            }
        }
    }

    // ---------------------------------------------------
    // Gateway orchestration service
    // ---------------------------------------------------

    static class GatewayService {

        private final ClientRegistry clients;
        private final Router router;
        private final RateLimiter limiter;
        private final UpstreamRegistry upstreams;
        private final AuditService audit;

        GatewayService(
                ClientRegistry clients,
                Router router,
                RateLimiter limiter,
                UpstreamRegistry upstreams,
                AuditService audit
        ) {
            this.clients = clients;
            this.router = router;
            this.limiter = limiter;
            this.upstreams = upstreams;
            this.audit = audit;
        }

        GatewayResponse handle(GatewayRequest request) {

            String clientId = "anonymous";
            int status = 500;

            try {

                RouteMatch match = router.resolve(
                        request.method(),
                        request.path()
                );

                if (match == null) {
                    throw new GatewayException(
                            404,
                            "NOT_FOUND",
                            "Route not found"
                    );
                }

                ApiClient client = clients.authenticate(request);

                clientId = client.clientId();

                clients.authorize(
                        client,
                        match.route().requiredScope()
                );

                if (!limiter.allow(client, match.route())) {
                    throw new GatewayException(
                            429,
                            "RATE_LIMITED",
                            "Rate limit exceeded"
                    );
                }

                GatewayResponse upstreamResponse =
                        upstreams.forward(
                                match.route().upstream(),
                                request,
                                match.parameters()
                        );

                status = upstreamResponse.statusCode();

                Map<String, String> responseHeaders =
                        new HashMap<>(upstreamResponse.headers());

                responseHeaders.put(
                        "X-Request-ID",
                        request.requestId()
                );

                responseHeaders.put(
                        "X-RateLimit-Remaining",
                        String.valueOf(
                                limiter.remaining(
                                        client,
                                        match.route()
                                )
                        )
                );

                return new GatewayResponse(
                        status,
                        upstreamResponse.body(),
                        responseHeaders
                );

            } catch (GatewayException exception) {

                status = exception.getStatusCode();

                return new GatewayResponse(
                        status,
                        Map.of(
                                "error", exception.getErrorCode(),
                                "message", exception.getMessage()
                        ),
                        Map.of(
                                "X-Request-ID",
                                request.requestId()
                        )
                );

            } catch (RuntimeException exception) {

                status = 502;

                return new GatewayResponse(
                        status,
                        Map.of(
                                "error", "GATEWAY_FAILURE",
                                "message", "Upstream processing failed"
                        ),
                        Map.of(
                                "X-Request-ID",
                                request.requestId()
                        )
                );

            } finally {
                audit.record(request, clientId, status);
            }
        }
    }

    // ---------------------------------------------------
    // Application configuration
    // ---------------------------------------------------

    static GatewayService buildGateway(AuditService audit) {

        ClientRegistry clients = new ClientRegistry();

        clients.register(new ApiClient(
                "client-001",
                "demo-user-token",
                Set.of("users:read", "orders:create"),
                ClientStatus.ACTIVE
        ));

        clients.register(new ApiClient(
                "client-002",
                "demo-admin-token",
                Set.of(
                        "users:read",
                        "users:delete",
                        "orders:create"
                ),
                ClientStatus.ACTIVE
        ));

        Router router = new Router();

        router.register(new RouteDefinition(
                "get-user",
                HttpMethod.GET,
                "/api/v1/users/{userId}",
                "users",
                "users:read",
                3,
                5
        ));

        router.register(new RouteDefinition(
                "create-order",
                HttpMethod.POST,
                "/api/v1/orders",
                "orders",
                "orders:create",
                5,
                10
        ));

        UpstreamRegistry upstreams = new UpstreamRegistry();

        upstreams.register("users", new UserService());
        upstreams.register("orders", new OrderService());

        return new GatewayService(
                clients,
                router,
                new RateLimiter(),
                upstreams,
                audit
        );
    }

    // ---------------------------------------------------
    // Demonstration and validation
    // ---------------------------------------------------

    public static void main(String[] args) {

        AuditService audit = new AuditService();

        GatewayService gateway = buildGateway(audit);

        GatewayRequest userRequest = new GatewayRequest(
                HttpMethod.GET,
                "/api/v1/users/101",
                Map.of(
                        "Authorization",
                        "Bearer demo-user-token"
                ),
                Map.of(),
                null
        );

        GatewayRequest orderRequest = new GatewayRequest(
                HttpMethod.POST,
                "/api/v1/orders",
                Map.of(
                        "Authorization",
                        "Bearer demo-user-token"
                ),
                Map.of("amount", 2500),
                null
        );

        GatewayRequest unauthorizedRequest = new GatewayRequest(
                HttpMethod.GET,
                "/api/v1/users/101",
                Map.of(),
                Map.of(),
                null
        );

        GatewayRequest missingRouteRequest = new GatewayRequest(
                HttpMethod.GET,
                "/api/v1/unknown",
                Map.of(
                        "Authorization",
                        "Bearer demo-user-token"
                ),
                Map.of(),
                null
        );

        List<GatewayRequest> requests = List.of(
                userRequest,
                orderRequest,
                unauthorizedRequest,
                missingRouteRequest
        );

        for (GatewayRequest request : requests) {

            GatewayResponse response = gateway.handle(request);

            System.out.println(
                    request.method() + " " +
                    request.path() + " -> " +
                    response.statusCode() + " " +
                    response.body()
            );
        }

        if (gateway.handle(userRequest).statusCode() != 200) {
            throw new AssertionError("User routing failed");
        }

        if (gateway.handle(orderRequest).statusCode() != 201) {
            throw new AssertionError("Order routing failed");
        }

        if (gateway.handle(unauthorizedRequest).statusCode() != 401) {
            throw new AssertionError("Authentication test failed");
        }

        if (gateway.handle(missingRouteRequest).statusCode() != 404) {
            throw new AssertionError("Route test failed");
        }

        System.out.println("\nAUDIT REPORT");

        audit.report().forEach((status, count) ->
                System.out.println(
                        "HTTP " + status + ": " + count
                )
        );

        System.out.println("\nAll Java 17 gateway tests passed.");
    }
}
