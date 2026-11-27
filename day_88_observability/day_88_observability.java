import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/**
 * Enterprise observability and centralized logging model.
 *
 * Demonstrates:
 * - Immutable structured events
 * - Trace and correlation context
 * - Centralized ingestion
 * - Asynchronous processing
 * - Redaction policies
 * - Service-level observability
 * - Alert policies
 * - Operational governance
 */
public class ObservabilityEnterprise {

    // -----------------------------------------------------
    // 1. Domain enums
    // -----------------------------------------------------

    enum Severity {
        DEBUG(10),
        INFO(20),
        WARNING(30),
        ERROR(40),
        CRITICAL(50);

        private final int value;

        Severity(int value) {
            this.value = value;
        }

        public int value() {
            return value;
        }
    }

    enum Environment {
        DEVELOPMENT,
        TESTING,
        STAGING,
        PRODUCTION
    }

    enum PipelineState {
        RUNNING,
        DRAINING,
        CLOSED
    }

    // -----------------------------------------------------
    // 2. Domain exceptions
    // -----------------------------------------------------

    static class ObservabilityException extends RuntimeException {
        ObservabilityException(String message) {
            super(message);
        }
    }

    static class ValidationException extends ObservabilityException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class CapacityException extends ObservabilityException {
        CapacityException(String message) {
            super(message);
        }
    }

    // -----------------------------------------------------
    // 3. Immutable tracing context
    // -----------------------------------------------------

    record TraceContext(
        String traceId,
        String spanId,
        String correlationId,
        String requestId,
        String tenantId
    ) {
        TraceContext {
            Objects.requireNonNull(traceId);
            Objects.requireNonNull(spanId);
            Objects.requireNonNull(correlationId);
            Objects.requireNonNull(requestId);

            if (
                traceId.isBlank() ||
                spanId.isBlank() ||
                correlationId.isBlank() ||
                requestId.isBlank()
            ) {
                throw new ValidationException(
                    "Trace context identifiers cannot be empty"
                );
            }
        }

        static TraceContext create(String correlationId) {
            return new TraceContext(
                UUID.randomUUID().toString(),
                UUID.randomUUID().toString(),
                correlationId,
                UUID.randomUUID().toString(),
                "tenant-default"
            );
        }

        TraceContext childSpan() {
            return new TraceContext(
                traceId,
                UUID.randomUUID().toString(),
                correlationId,
                requestId,
                tenantId
            );
        }
    }

    // -----------------------------------------------------
    // 4. Structured event model
    // -----------------------------------------------------

    record LogEvent(
        long sequence,
        Instant timestamp,
        Severity severity,
        String service,
        Environment environment,
        String version,
        String eventName,
        String message,
        TraceContext context,
        Map<String, String> attributes
    ) {
        LogEvent {
            Objects.requireNonNull(timestamp);
            Objects.requireNonNull(severity);
            Objects.requireNonNull(environment);
            Objects.requireNonNull(context);

            if (
                service == null || service.isBlank() ||
                version == null || version.isBlank() ||
                eventName == null || eventName.isBlank() ||
                message == null
            ) {
                throw new ValidationException(
                    "Invalid structured log event"
                );
            }

            attributes = Collections.unmodifiableMap(
                new LinkedHashMap<>(attributes)
            );
        }
    }

    // -----------------------------------------------------
    // 5. Security policy
    // -----------------------------------------------------

    static final class RedactionPolicy {

        private final Set<String> sensitiveKeys = Set.of(
            "password",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "authorization",
            "api_key",
            "credit_card"
        );

        private final Set<String> allowedKeys = Set.of(
            "amount",
            "payment_id",
            "duration_ms",
            "error_type",
            "error_message",
            "status",
            "username",
            "user_id",
            "operation"
        );

        Map<String, String> sanitize(
            Map<String, String> input
        ) {
            Map<String, String> result = new LinkedHashMap<>();

            for (Map.Entry<String, String> entry :
                 input.entrySet()) {

                String key = entry.getKey();

                if (key == null || key.isBlank()) {
                    throw new ValidationException(
                        "Attribute key cannot be empty"
                    );
                }

                String normalized = key.toLowerCase();

                String value = entry.getValue();

                if (sensitiveKeys.contains(normalized)) {
                    result.put(key, "[REDACTED]");
                } else if (value == null) {
                    result.put(key, "[NULL]");
                } else if (!allowedKeys.contains(normalized)) {
                    result.put(key, "[OMITTED_BY_POLICY]");
                } else {
                    result.put(
                        key,
                        value.replaceAll(
                            "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}",
                            "[REDACTED_EMAIL]"
                        )
                    );
                }
            }

            return result;
        }
    }

    // -----------------------------------------------------
    // 6. Event construction service
    // -----------------------------------------------------

    static final class StructuredEventFactory {

        private final String service;
        private final Environment environment;
        private final String version;
        private final RedactionPolicy redactionPolicy;

        StructuredEventFactory(
            String service,
            Environment environment,
            String version,
            RedactionPolicy redactionPolicy
        ) {
            this.service = Objects.requireNonNull(service);
            this.environment = Objects.requireNonNull(environment);
            this.version = Objects.requireNonNull(version);
            this.redactionPolicy = redactionPolicy;

            if (service.isBlank() || version.isBlank()) {
                throw new ValidationException(
                    "Invalid service configuration"
                );
            }
        }

        LogEvent create(
            long sequence,
            Severity severity,
            String eventName,
            String message,
            TraceContext context,
            Map<String, String> attributes
        ) {
            return new LogEvent(
                sequence,
                Instant.now(),
                severity,
                service,
                environment,
                version,
                eventName,
                message,
                context,
                redactionPolicy.sanitize(attributes)
            );
        }
    }

    // -----------------------------------------------------
    // 7. Centralized asynchronous ingestion
    // -----------------------------------------------------

    static final class CentralLogService
        implements AutoCloseable {

        private final BlockingQueue<LogEvent> queue;
        private final List<LogEvent> storage =
            Collections.synchronizedList(new ArrayList<>());

        private final AtomicLong sequence = new AtomicLong();
        private final AtomicBoolean running =
            new AtomicBoolean(true);

        private final LongAdder rejected = new LongAdder();

        private final int maximumStored;

        private volatile PipelineState state =
            PipelineState.RUNNING;

        private final Thread worker;

        CentralLogService(
            int queueCapacity,
            int maximumStored
        ) {
            if (queueCapacity <= 0 || maximumStored <= 0) {
                throw new ValidationException(
                    "Capacities must be positive"
                );
            }

            this.queue = new ArrayBlockingQueue<>(queueCapacity);
            this.maximumStored = maximumStored;

            worker = new Thread(
                this::processQueue,
                "central-log-worker"
            );

            worker.start();
        }

        void publish(LogEvent event) {
            if (state != PipelineState.RUNNING) {
                throw new ObservabilityException(
                    "Log service is not accepting events"
                );
            }

            LogEvent sequenced = new LogEvent(
                sequence.incrementAndGet(),
                event.timestamp(),
                event.severity(),
                event.service(),
                event.environment(),
                event.version(),
                event.eventName(),
                event.message(),
                event.context(),
                event.attributes()
            );

            if (!queue.offer(sequenced)) {
                rejected.increment();

                throw new CapacityException(
                    "Centralized log queue is full"
                );
            }
        }

        private void processQueue() {
            while (
                running.get() ||
                !queue.isEmpty()
            ) {
                try {
                    LogEvent event = queue.poll(
                        100,
                        java.util.concurrent.TimeUnit.MILLISECONDS
                    );

                    if (event == null) {
                        continue;
                    }

                    synchronized (storage) {
                        storage.add(event);

                        if (storage.size() > maximumStored) {
                            storage.remove(0);
                        }
                    }

                } catch (InterruptedException error) {
                    if (!running.get()) {
                        break;
                    }

                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }

        List<LogEvent> query(
            Predicate<LogEvent> predicate
        ) {
            synchronized (storage) {
                return storage.stream()
                    .filter(predicate)
                    .sorted(Comparator.comparingLong(
                        LogEvent::sequence
                    ))
                    .collect(Collectors.toList());
            }
        }

        List<LogEvent> snapshot() {
            return query(event -> true);
        }

        long rejectedCount() {
            return rejected.sum();
        }

        PipelineState state() {
            return state;
        }

        @Override
        public void close() {
            if (state == PipelineState.CLOSED) {
                return;
            }

            state = PipelineState.DRAINING;
            running.set(false);

            try {
                worker.join(5000);

                if (worker.isAlive()) {
                    throw new CapacityException(
                        "Log worker did not drain within timeout"
                    );
                }

                state = PipelineState.CLOSED;

            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();

                throw new ObservabilityException(
                    "Interrupted during shutdown"
                );
            }
        }
    }

    // -----------------------------------------------------
    // 8. Application logging facade
    // -----------------------------------------------------

    static final class ApplicationLogger {

        private final StructuredEventFactory factory;
        private final CentralLogService centralService;
        private final AtomicLong localSequence =
            new AtomicLong();

        ApplicationLogger(
            StructuredEventFactory factory,
            CentralLogService centralService
        ) {
            this.factory = factory;
            this.centralService = centralService;
        }

        void log(
            Severity severity,
            String eventName,
            String message,
            TraceContext context,
            Map<String, String> attributes
        ) {
            LogEvent event = factory.create(
                localSequence.incrementAndGet(),
                severity,
                eventName,
                message,
                context,
                attributes
            );

            centralService.publish(event);
        }
    }

    // -----------------------------------------------------
    // 9. Enterprise payment service
    // -----------------------------------------------------

    static final class PaymentService {

        private final ApplicationLogger logger;

        PaymentService(ApplicationLogger logger) {
            this.logger = logger;
        }

        void process(
            double amount,
            TraceContext context,
            boolean fail
        ) {
            logger.log(
                Severity.INFO,
                "payment.started",
                "Payment processing started",
                context,
                Map.of(
                    "amount",
                    Double.toString(amount)
                )
            );

            try {
                if (!Double.isFinite(amount) || amount <= 0) {
                    throw new ValidationException(
                        "Payment amount must be positive"
                    );
                }

                CompletableFuture<Void> gatewayCall =
                    CompletableFuture.runAsync(() -> {
                        if (fail) {
                            throw new ObservabilityException(
                                "Payment gateway unavailable"
                            );
                        }
                    });

                gatewayCall.join();

                logger.log(
                    Severity.INFO,
                    "payment.completed",
                    "Payment completed",
                    context.childSpan(),
                    Map.of(
                        "amount",
                        Double.toString(amount),
                        "status",
                        "COMPLETED",
                        "payment_id",
                        UUID.randomUUID().toString()
                    )
                );

            } catch (RuntimeException error) {
                logger.log(
                    Severity.ERROR,
                    "payment.failed",
                    "Payment processing failed",
                    context,
                    Map.of(
                        "error_type", error.getClass().getSimpleName(),
                        "error_message", error.getMessage() == null
                            ? "Unknown failure"
                            : error.getMessage()
                    )
                );

                throw error;
            }
        }
    }

    // -----------------------------------------------------
    // 10. Alert policy and analytics
    // -----------------------------------------------------

    record AlertPolicy(
        String name,
        String service,
        double errorThreshold,
        int minimumEvents
    ) {
        AlertPolicy {
            if (
                name == null || name.isBlank() ||
                service == null || service.isBlank() ||
                errorThreshold < 0 ||
                errorThreshold > 1 ||
                minimumEvents <= 0
            ) {
                throw new ValidationException(
                    "Invalid alert policy"
                );
            }
        }
    }

    static final class ObservabilityAnalytics {

        private final CentralLogService centralService;

        ObservabilityAnalytics(
            CentralLogService centralService
        ) {
            this.centralService = centralService;
        }

        Map<String, Object> serviceReport(String service) {
            List<LogEvent> events = centralService.query(
                event -> event.service().equals(service)
            );

            long errors = events.stream()
                .filter(event ->
                    event.severity().value() >= Severity.ERROR.value()
                )
                .count();

            double rate = events.isEmpty()
                ? 0
                : (double) errors / events.size();

            Map<String, Long> distribution = events.stream()
                .collect(Collectors.groupingBy(
                    LogEvent::eventName,
                    Collectors.counting()
                ));

            Map<String, Object> report = new LinkedHashMap<>();

            report.put("service", service);
            report.put("total_events", events.size());
            report.put("errors", errors);
            report.put("error_rate", rate);
            report.put("distribution", distribution);

            return report;
        }

        boolean evaluate(AlertPolicy policy) {
            Map<String, Object> report =
                serviceReport(policy.service());

            int total = (int) report.get("total_events");
            double rate = (double) report.get("error_rate");

            return total >= policy.minimumEvents()
                && rate >= policy.errorThreshold();
        }
    }

    // -----------------------------------------------------
    // 11. JSON-compatible display
    // -----------------------------------------------------

    static String jsonEscape(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }

    static String serialize(LogEvent event) {
        StringBuilder json = new StringBuilder();

        json.append("{")
            .append("\"sequence\":").append(event.sequence())
            .append(",\"timestamp\":\"")
            .append(event.timestamp())
            .append("\",\"severity\":\"")
            .append(event.severity())
            .append("\",\"service\":\"")
            .append(jsonEscape(event.service()))
            .append("\",\"event_name\":\"")
            .append(jsonEscape(event.eventName()))
            .append("\",\"message\":\"")
            .append(jsonEscape(event.message()))
            .append("\",\"trace_id\":\"")
            .append(jsonEscape(event.context().traceId()))
            .append("\",\"correlation_id\":\"")
            .append(jsonEscape(event.context().correlationId()))
            .append("\",\"attributes\":{");

        boolean first = true;

        for (Map.Entry<String, String> entry :
             event.attributes().entrySet()) {

            if (!first) {
                json.append(",");
            }

            first = false;

            json.append("\"")
                .append(jsonEscape(entry.getKey()))
                .append("\":\"")
                .append(jsonEscape(entry.getValue()))
                .append("\"");
        }

        return json.append("}}").toString();
    }

    // -----------------------------------------------------
    // 12. Enterprise demonstration
    // -----------------------------------------------------

    public static void main(String[] args) {

        try (
            CentralLogService centralService =
                new CentralLogService(1000, 5000)
        ) {
            RedactionPolicy redactionPolicy =
                new RedactionPolicy();

            StructuredEventFactory factory =
                new StructuredEventFactory(
                    "payment-platform",
                    Environment.PRODUCTION,
                    "4.1.0",
                    redactionPolicy
                );

            ApplicationLogger logger =
                new ApplicationLogger(
                    factory,
                    centralService
                );

            PaymentService paymentService =
                new PaymentService(logger);

            TraceContext context =
                TraceContext.create("order-2026-5001");

            paymentService.process(
                2200.00,
                context,
                false
            );

            try {
                paymentService.process(
                    400.00,
                    context,
                    true
                );
            } catch (RuntimeException expected) {
                System.out.println(
                    "Expected gateway failure recorded."
                );
            }

            try {
                paymentService.process(
                    -10.00,
                    context,
                    false
                );
            } catch (RuntimeException expected) {
                System.out.println(
                    "Expected validation failure recorded."
                );
            }

            logger.log(
                Severity.WARNING,
                "authentication.failure",
                "Authentication attempt failed",
                context,
                Map.of(
                    "username", "operator",
                    "password", "example-password",
                    "access_token", "sensitive-token"
                )
            );

            // Wait until the asynchronous collector has processed
            // every event before performing reporting operations.
            while (
                centralService.query(event -> true).size() < 7
            ) {
                try {
                    Thread.sleep(10);
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new ObservabilityException(
                        "Interrupted while awaiting log ingestion"
                    );
                }
            }

            ObservabilityAnalytics analytics =
                new ObservabilityAnalytics(centralService);

            System.out.println("\nSERVICE REPORT");

            System.out.println(
                analytics.serviceReport("payment-platform")
            );

            AlertPolicy policy = new AlertPolicy(
                "payment-error-policy",
                "payment-platform",
                0.25,
                3
            );

            System.out.println("\nALERT STATUS");

            System.out.println(
                analytics.evaluate(policy)
                    ? "FIRING"
                    : "NORMAL"
            );

            System.out.println("\nCENTRALIZED EVENTS");

            for (LogEvent event : centralService.snapshot()) {
                System.out.println(serialize(event));
            }

            List<LogEvent> traceEvents =
                centralService.query(
                    event -> event.context().traceId()
                        .equals(context.traceId())
                );

            System.out.println("\nTRACE EVENTS: " + traceEvents.size());

            LogEvent securityEvent = centralService.query(
                event -> event.eventName()
                    .equals("authentication.failure")
            ).get(0);

            if (
                !securityEvent.attributes().get("password")
                    .equals("[REDACTED]")
            ) {
                throw new IllegalStateException(
                    "Password redaction failed"
                );
            }

            if (
                !securityEvent.attributes().get("access_token")
                    .equals("[REDACTED]")
            ) {
                throw new IllegalStateException(
                    "Token redaction failed"
                );
            }

            if (traceEvents.size() != 7) {
                throw new IllegalStateException(
                    "Unexpected trace event count"
                );
            }

            System.out.println(
                "\nEnterprise validation successful."
            );
        }
    }
}
