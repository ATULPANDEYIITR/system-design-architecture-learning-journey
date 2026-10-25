import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class ReverseProxyApplication {

    enum Protocol {
        HTTP,
        HTTPS
    }

    enum ServerState {
        HEALTHY,
        UNHEALTHY
    }

    enum ProxyStatus {
        SUCCESS,
        BAD_REQUEST,
        TLS_FAILURE,
        UPSTREAM_FAILURE
    }

    record TLSCertificate(
        String hostname,
        String issuer
    ) {}

    record Route(
        String prefix,
        String upstreamGroup
    ) {}

    record Request(
        String clientIp,
        String host,
        String method,
        String path,
        Protocol protocol,
        Map<String, String> headers,
        String body
    ) {}

    record ProxyResponse(
        int status,
        String body,
        String upstream,
        ProxyStatus proxyStatus
    ) {}

    static final class ProxyException extends RuntimeException {
        ProxyException(String message) {
            super(message);
        }
    }

    static final class RequestException extends ProxyException {
        RequestException(String message) {
            super(message);
        }
    }

    static final class TLSException extends ProxyException {
        TLSException(String message) {
            super(message);
        }
    }

    static final class UpstreamException extends ProxyException {
        UpstreamException(String message) {
            super(message);
        }
    }

    static final class UpstreamServer {
        private final String name;
        private final String address;
        private final int port;
        private final int weight;

        private ServerState state = ServerState.HEALTHY;
        private int requests;
        private int activeConnections;

        UpstreamServer(
            String name,
            String address,
            int port,
            int weight
        ) {
            if (weight <= 0) {
                throw new IllegalArgumentException(
                    "weight must be positive"
                );
            }

            this.name = name;
            this.address = address;
            this.port = port;
            this.weight = weight;
        }

        boolean isHealthy() {
            return state == ServerState.HEALTHY;
        }

        void setHealthy(boolean healthy) {
            state = healthy
                ? ServerState.HEALTHY
                : ServerState.UNHEALTHY;
        }

        void beginRequest() {
            activeConnections++;
            requests++;
        }

        void endRequest() {
            activeConnections--;

            if (activeConnections < 0) {
                activeConnections = 0;
                throw new IllegalStateException(
                    "connection accounting underflow"
                );
            }
        }

        String getName() {
            return name;
        }

        int getRequests() {
            return requests;
        }

        int getActiveConnections() {
            return activeConnections;
        }

        ServerState getState() {
            return state;
        }

        int getWeight() {
            return weight;
        }
    }

    static final class TLSManager {
        private final Map<String, TLSCertificate> certificates =
            new HashMap<>();

        TLSManager(List<TLSCertificate> certificates) {
            for (TLSCertificate certificate : certificates) {
                this.certificates.put(
                    certificate.hostname(),
                    certificate
                );
            }
        }

        void terminate(String host, String tlsVersion) {
            if (!certificates.containsKey(host)) {
                throw new TLSException(
                    "certificate unavailable for " + host
                );
            }

            if (!Set.of("TLS1.2", "TLS1.3")
                    .contains(tlsVersion)) {
                throw new TLSException(
                    "TLS version rejected: " + tlsVersion
                );
            }
        }
    }

    static final class WeightedBalancer {
        private final Map<String, Integer> positions =
            new HashMap<>();

        UpstreamServer choose(
            String group,
            List<UpstreamServer> servers,
            Set<String> excluded
        ) {
            List<UpstreamServer> weighted =
                new ArrayList<>();

            for (UpstreamServer server : servers) {
                if (!server.isHealthy() ||
                    excluded.contains(server.getName())) {
                    continue;
                }

                for (int i = 0;
                     i < server.getWeight();
                     i++) {
                    weighted.add(server);
                }
            }

            if (weighted.isEmpty()) {
                throw new UpstreamException(
                    "no healthy upstream in " + group
                );
            }

            int position = positions.getOrDefault(group, 0);
            UpstreamServer selected =
                weighted.get(position % weighted.size());

            positions.put(group, position + 1);
            return selected;
        }
    }

    static final class RepositoryStyleAuditEvent {
        final Instant timestamp;
        final String requestId;
        final String path;
        final int status;
        final String upstream;

        RepositoryStyleAuditEvent(
            String requestId,
            String path,
            int status,
            String upstream
        ) {
            this.timestamp = Instant.now();
            this.requestId = requestId;
            this.path = path;
            this.status = status;
            this.upstream = upstream;
        }

        @Override
        public String toString() {
            return timestamp
                + " requestId=" + requestId
                + " path=" + path
                + " status=" + status
                + " upstream=" + upstream;
        }
    }

    static final class ReverseProxyService {
        private final TLSManager tlsManager;
        private final Map<String, List<UpstreamServer>> pools;
        private final List<Route> routes;
        private final WeightedBalancer balancer =
            new WeightedBalancer();
        private final List<RepositoryStyleAuditEvent> auditEvents =
            new ArrayList<>();

        ReverseProxyService(
            TLSManager tlsManager,
            Map<String, List<UpstreamServer>> pools,
            List<Route> routes
        ) {
            this.tlsManager = tlsManager;
            this.pools = Map.copyOf(pools);
            this.routes = List.copyOf(routes);
        }

        private void validate(Request request) {
            if (request.clientIp() == null ||
                request.clientIp().isBlank()) {
                throw new RequestException(
                    "client IP is required"
                );
            }

            if (!Set.of(
                    "GET",
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE"
                ).contains(request.method())) {
                throw new RequestException(
                    "unsupported HTTP method"
                );
            }

            if (request.path() == null ||
                !request.path().startsWith("/")) {
                throw new RequestException(
                    "invalid URI"
                );
            }

            if (request.path().length() > 4096) {
                throw new RequestException(
                    "URI exceeds configured limit"
                );
            }

            if (request.path().contains("\r") ||
                request.path().contains("\n")) {
                throw new RequestException(
                    "CRLF injection attempt rejected"
                );
            }

            if (request.body() != null &&
                request.body()
                    .getBytes()
                    .length > 1_000_000) {
                throw new RequestException(
                    "request body too large"
                );
            }

            if (request.headers()
                    .containsKey("X-Forwarded-For")) {
                throw new RequestException(
                    "untrusted client supplied X-Forwarded-For"
                );
            }
        }

        private Route resolveRoute(String path) {
            Route selected = null;

            for (Route route : routes) {
                if (path.startsWith(route.prefix()) &&
                    (selected == null ||
                     route.prefix().length() >
                     selected.prefix().length())) {
                    selected = route;
                }
            }

            if (selected == null) {
                throw new RequestException(
                    "no configured route"
                );
            }

            return selected;
        }

        private ProxyResponse send(
            UpstreamServer server,
            Request request
        ) {
            server.beginRequest();

            try {
                if (request.path().equals("/api/failure") &&
                    server.getName().equals("api-1")) {
                    throw new UpstreamException(
                        "simulated transport failure"
                    );
                }

                String requestId =
                    UUID.randomUUID().toString();

                String body =
                    "{"
                    + "\"requestId\":\"" + requestId + "\","
                    + "\"upstream\":\""
                    + server.getName() + "\","
                    + "\"path\":\""
                    + request.path() + "\","
                    + "\"forwardedFor\":\""
                    + request.clientIp() + "\""
                    + "}";

                return new ProxyResponse(
                    200,
                    body,
                    server.getName(),
                    ProxyStatus.SUCCESS
                );
            } finally {
                server.endRequest();
            }
        }

        ProxyResponse handle(Request request) {
            String requestId = UUID.randomUUID().toString();

            try {
                validate(request);

                if (request.protocol() == Protocol.HTTPS) {
                    String version =
                        request.headers()
                            .getOrDefault(
                                "X-TLS-Version",
                                "TLS1.3"
                            );

                    // The proxy is the TLS endpoint. The application
                    // server is separated from client TLS policy.
                    tlsManager.terminate(
                        request.host(),
                        version
                    );
                }

                Route route =
                    resolveRoute(request.path());

                List<UpstreamServer> servers =
                    pools.get(route.upstreamGroup());

                if (servers == null) {
                    throw new UpstreamException(
                        "unknown upstream group"
                    );
                }

                Set<String> excluded = new HashSet<>();
                ProxyResponse response = null;

                for (int attempt = 0; attempt < 2; attempt++) {
                    UpstreamServer server =
                        balancer.choose(
                            route.upstreamGroup(),
                            servers,
                            excluded
                        );

                    excluded.add(server.getName());

                    try {
                        response = send(server, request);
                        break;
                    } catch (UpstreamException error) {
                        if (attempt == 1) {
                            throw error;
                        }
                    }
                }

                if (response == null) {
                    throw new UpstreamException(
                        "retry limit reached"
                    );
                }

                auditEvents.add(
                    new RepositoryStyleAuditEvent(
                        requestId,
                        request.path(),
                        response.status(),
                        response.upstream()
                    )
                );

                return response;
            } catch (TLSException error) {
                ProxyResponse response =
                    new ProxyResponse(
                        495,
                        error.getMessage(),
                        null,
                        ProxyStatus.TLS_FAILURE
                    );

                auditEvents.add(
                    new RepositoryStyleAuditEvent(
                        requestId,
                        request.path(),
                        495,
                        null
                    )
                );

                return response;
            } catch (RequestException error) {
                ProxyResponse response =
                    new ProxyResponse(
                        400,
                        error.getMessage(),
                        null,
                        ProxyStatus.BAD_REQUEST
                    );

                auditEvents.add(
                    new RepositoryStyleAuditEvent(
                        requestId,
                        request.path(),
                        400,
                        null
                    )
                );

                return response;
            } catch (UpstreamException error) {
                ProxyResponse response =
                    new ProxyResponse(
                        503,
                        error.getMessage(),
                        null,
                        ProxyStatus.UPSTREAM_FAILURE
                    );

                auditEvents.add(
                    new RepositoryStyleAuditEvent(
                        requestId,
                        request.path(),
                        503,
                        null
                    )
                );

                return response;
            }
        }

        void setHealth(
            String group,
            String serverName,
            boolean healthy
        ) {
            List<UpstreamServer> servers =
                pools.get(group);

            if (servers == null) {
                throw new IllegalArgumentException(
                    "unknown pool"
                );
            }

            for (UpstreamServer server : servers) {
                if (server.getName().equals(serverName)) {
                    server.setHealthy(healthy);
                    return;
                }
            }

            throw new IllegalArgumentException(
                "unknown server"
            );
        }

        void printAuditEvents() {
            System.out.println("\nAudit events:");

            for (RepositoryStyleAuditEvent event :
                auditEvents) {
                System.out.println(event);
            }
        }

        void printStatistics() {
            System.out.println("\nUpstream statistics:");

            for (Map.Entry<String, List<UpstreamServer>> entry :
                pools.entrySet()) {
                System.out.println(entry.getKey());

                for (UpstreamServer server :
                    entry.getValue()) {
                    System.out.println(
                        "  "
                        + server.getName()
                        + " state="
                        + server.getState()
                        + " requests="
                        + server.getRequests()
                        + " active="
                        + server.getActiveConnections()
                    );
                }
            }
        }
    }

    public static void main(String[] args) {
        TLSManager tlsManager =
            new TLSManager(
                List.of(
                    new TLSCertificate(
                        "api.example.com",
                        "Example CA"
                    )
                )
            );

        List<UpstreamServer> apiServers =
            new ArrayList<>(
                List.of(
                    new UpstreamServer(
                        "api-1",
                        "10.0.1.10",
                        8080,
                        2
                    ),
                    new UpstreamServer(
                        "api-2",
                        "10.0.1.11",
                        8080,
                        1
                    )
                )
            );

        List<UpstreamServer> webServers =
            new ArrayList<>(
                List.of(
                    new UpstreamServer(
                        "web-1",
                        "10.0.2.10",
                        8080,
                        1
                    ),
                    new UpstreamServer(
                        "web-2",
                        "10.0.2.11",
                        8080,
                        1
                    )
                )
            );

        Map<String, List<UpstreamServer>> pools =
            Map.of(
                "api", apiServers,
                "web", webServers
            );

        List<Route> routes =
            List.of(
                new Route("/api/", "api"),
                new Route("/", "web")
            );

        ReverseProxyService proxy =
            new ReverseProxyService(
                tlsManager,
                pools,
                routes
            );

        List<Request> requests =
            List.of(
                new Request(
                    "203.0.113.10",
                    "api.example.com",
                    "GET",
                    "/api/users",
                    Protocol.HTTPS,
                    Map.of("X-TLS-Version", "TLS1.3"),
                    ""
                ),
                new Request(
                    "203.0.113.11",
                    "api.example.com",
                    "GET",
                    "/",
                    Protocol.HTTPS,
                    Map.of("X-TLS-Version", "TLS1.2"),
                    ""
                ),
                new Request(
                    "203.0.113.12",
                    "api.example.com",
                    "GET",
                    "/api/failure",
                    Protocol.HTTPS,
                    Map.of(),
                    ""
                ),
                new Request(
                    "203.0.113.13",
                    "api.example.com",
                    "GET",
                    "/api/users",
                    Protocol.HTTPS,
                    Map.of(
                        "X-Forwarded-For",
                        "198.51.100.10"
                    ),
                    ""
                )
            );

        for (Request request : requests) {
            ProxyResponse response =
                proxy.handle(request);

            System.out.println(
                "\nstatus=" + response.status()
                + " upstream=" + response.upstream()
                + " state=" + response.proxyStatus()
                + "\n" + response.body()
            );
        }

        proxy.setHealth(
            "api",
            "api-1",
            false
        );

        ProxyResponse fallback =
            proxy.handle(
                new Request(
                    "203.0.113.20",
                    "api.example.com",
                    "GET",
                    "/api/orders",
                    Protocol.HTTPS,
                    Map.of(),
                    ""
                )
            );

        System.out.println(
            "\nFallback status="
            + fallback.status()
            + " upstream="
            + fallback.upstream()
        );

        proxy.printStatistics();
        proxy.printAuditEvents();
    }
}
