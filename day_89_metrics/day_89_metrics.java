import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAdder;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

/**
 * Enterprise metrics and SLI management.
 *
 * Java 17, standard library only.
 */
public class MetricsEnterprise {

    enum MetricType {
        COUNTER,
        GAUGE,
        HISTOGRAM
    }

    enum HealthState {
        HEALTHY,
        DEGRADED,
        BREACHED,
        NO_DATA
    }

    static class MetricsException extends RuntimeException {
        MetricsException(String message) {
            super(message);
        }
    }

    record MetricKey(Map<String, String> labels) {
        MetricKey {
            labels = Collections.unmodifiableMap(
                new TreeMap<>(labels)
            );
        }
    }

    interface Metric {
        String name();

        MetricType type();

        Map<String, Object> snapshot();
    }

    static void validateName(String name) {
        if (
            name == null ||
            !name.matches("[a-zA-Z_:][a-zA-Z0-9_:]*")
        ) {
            throw new MetricsException("Invalid metric name.");
        }
    }

    static void validateLabels(
        Map<String, String> labels,
        List<String> required
    ) {
        Objects.requireNonNull(labels);

        if (labels.size() > 10 ||
            !labels.keySet().equals(
                new java.util.HashSet<>(required)
            )) {
            throw new MetricsException("Invalid metric labels.");
        }

        labels.forEach((key, value) -> {
            validateName(key);

            if (value == null || value.length() > 128) {
                throw new MetricsException("Invalid label value.");
            }
        });
    }

    static class Counter implements Metric {
        private final String name;
        private final List<String> labelNames;

        private final ConcurrentHashMap<MetricKey, DoubleAdder>
            values = new ConcurrentHashMap<>();

        Counter(String name, String... labelNames) {
            validateName(name);

            this.name = name;
            this.labelNames = List.of(labelNames);
        }

        public String name() {
            return name;
        }

        public MetricType type() {
            return MetricType.COUNTER;
        }

        public double increment(
            double amount,
            Map<String, String> labels
        ) {
            if (!Double.isFinite(amount) || amount <= 0) {
                throw new MetricsException(
                    "Counter increment must be positive."
                );
            }

            validateLabels(labels, labelNames);

            MetricKey key = new MetricKey(labels);

            DoubleAdder adder = values.computeIfAbsent(
                key,
                ignored -> new DoubleAdder()
            );

            adder.add(amount);
            return adder.sum();
        }

        public double get(Map<String, String> labels) {
            validateLabels(labels, labelNames);

            DoubleAdder adder = values.get(
                new MetricKey(labels)
            );

            return adder == null ? 0 : adder.sum();
        }

        public Map<String, Object> snapshot() {
            Map<String, Object> result = new TreeMap<>();

            values.forEach((key, value) ->
                result.put(
                    key.labels().toString(),
                    value.sum()
                )
            );

            return result;
        }
    }

    static class Gauge implements Metric {
        private final String name;

        private final ConcurrentHashMap<MetricKey, AtomicReference<Double>>
            values = new ConcurrentHashMap<>();

        private final List<String> labelNames;

        Gauge(String name, String... labelNames) {
            validateName(name);

            this.name = name;
            this.labelNames = List.of(labelNames);
        }

        public String name() {
            return name;
        }

        public MetricType type() {
            return MetricType.GAUGE;
        }

        public double set(
            double value,
            Map<String, String> labels
        ) {
            if (!Double.isFinite(value)) {
                throw new MetricsException("Invalid gauge value.");
            }

            validateLabels(labels, labelNames);

            MetricKey key = new MetricKey(labels);

            values.computeIfAbsent(
                key,
                ignored -> new AtomicReference<>(0.0)
            ).set(value);

            return value;
        }

        public double add(
            double amount,
            Map<String, String> labels
        ) {
            if (!Double.isFinite(amount)) {
                throw new MetricsException("Invalid gauge delta.");
            }

            validateLabels(labels, labelNames);

            MetricKey key = new MetricKey(labels);

            AtomicReference<Double> reference =
                values.computeIfAbsent(
                    key,
                    ignored -> new AtomicReference<>(0.0)
                );

            return reference.updateAndGet(v -> v + amount);
        }

        public double get(Map<String, String> labels) {
            validateLabels(labels, labelNames);

            AtomicReference<Double> value =
                values.get(new MetricKey(labels));

            return value == null ? 0 : value.get();
        }

        public Map<String, Object> snapshot() {
            Map<String, Object> result = new TreeMap<>();

            values.forEach((key, value) ->
                result.put(key.labels().toString(), value.get())
            );

            return result;
        }
    }

    static class Histogram implements Metric {
        private final String name;
        private final double[] boundaries;
        private final List<String> labelNames;

        private static class Series {
            final LongAdder count = new LongAdder();
            final DoubleAdder sum = new DoubleAdder();
            final LongAdder[] buckets;
            final List<Double> samples =
                Collections.synchronizedList(new ArrayList<>());

            Series(int bucketCount) {
                buckets = new LongAdder[bucketCount];

                for (int i = 0; i < bucketCount; i++) {
                    buckets[i] = new LongAdder();
                }
            }
        }

        private final ConcurrentHashMap<MetricKey, Series>
            series = new ConcurrentHashMap<>();

        Histogram(
            String name,
            double[] boundaries,
            String... labelNames
        ) {
            validateName(name);

            if (boundaries.length == 0) {
                throw new MetricsException("Histogram needs buckets.");
            }

            this.boundaries = boundaries.clone();

            for (int i = 0; i < boundaries.length; i++) {
                if (
                    !Double.isFinite(boundaries[i]) ||
                    boundaries[i] <= 0 ||
                    (i > 0 && boundaries[i] <= boundaries[i - 1])
                ) {
                    throw new MetricsException(
                        "Buckets must be positive and sorted."
                    );
                }
            }

            this.name = name;
            this.labelNames = List.of(labelNames);
        }

        public String name() {
            return name;
        }

        public MetricType type() {
            return MetricType.HISTOGRAM;
        }

        public void observe(
            double value,
            Map<String, String> labels
        ) {
            if (!Double.isFinite(value) || value < 0) {
                throw new MetricsException(
                    "Invalid histogram observation."
                );
            }

            validateLabels(labels, labelNames);

            Series s = series.computeIfAbsent(
                new MetricKey(labels),
                ignored -> new Series(boundaries.length)
            );

            s.count.increment();
            s.sum.add(value);

            for (int i = 0; i < boundaries.length; i++) {
                if (value <= boundaries[i]) {
                    s.buckets[i].increment();
                }
            }

            // Bounded local samples prevent unbounded memory growth.
            synchronized (s.samples) {
                if (s.samples.size() >= 10000) {
                    s.samples.remove(0);
                }

                s.samples.add(value);
            }
        }

        public Double percentile(
            double quantile,
            Map<String, String> labels
        ) {
            if (quantile < 0 || quantile > 1) {
                throw new MetricsException("Invalid quantile.");
            }

            validateLabels(labels, labelNames);

            Series s = series.get(new MetricKey(labels));

            if (s == null) {
                return null;
            }

            List<Double> sorted;

            synchronized (s.samples) {
                sorted = new ArrayList<>(s.samples);
            }

            if (sorted.isEmpty()) {
                return null;
            }

            sorted.sort(Comparator.naturalOrder());

            int index = Math.max(
                0,
                (int) Math.ceil(quantile * sorted.size()) - 1
            );

            return sorted.get(index);
        }

        public Map<String, Object> snapshot() {
            Map<String, Object> result = new TreeMap<>();

            series.forEach((key, s) -> {
                Map<String, Object> item = new TreeMap<>();

                item.put("count", s.count.sum());
                item.put("sum", s.sum.sum());

                Map<Double, Long> bucketValues = new TreeMap<>();

                for (int i = 0; i < boundaries.length; i++) {
                    bucketValues.put(
                        boundaries[i],
                        s.buckets[i].sum()
                    );
                }

                item.put("buckets", bucketValues);
                item.put("infinity", s.count.sum());

                result.put(key.labels().toString(), item);
            });

            return result;
        }
    }

    record SLIResult(
        String name,
        double good,
        double total,
        Double value,
        double target,
        Boolean passed,
        Instant evaluatedAt
    ) {}

    static class SLIPolicy {
        private final String name;
        private final double target;

        SLIPolicy(String name, double target) {
            if (
                target < 0 ||
                target > 1 ||
                !Double.isFinite(target)
            ) {
                throw new MetricsException("Invalid SLI target.");
            }

            this.name = name;
            this.target = target;
        }

        SLIResult evaluate(double good, double total) {
            if (
                !Double.isFinite(good) ||
                !Double.isFinite(total) ||
                total < 0 ||
                good < 0 ||
                good > total
            ) {
                throw new MetricsException("Invalid SLI data.");
            }

            if (total == 0) {
                return new SLIResult(
                    name,
                    good,
                    total,
                    null,
                    target,
                    null,
                    Instant.now()
                );
            }

            double value = good / total;

            return new SLIResult(
                name,
                good,
                total,
                value,
                target,
                value >= target,
                Instant.now()
            );
        }
    }

    record ServiceLevelObjective(
        String name,
        double target,
        double errorBudget
    ) {
        ServiceLevelObjective {
            if (
                target < 0 || target > 1 ||
                errorBudget < 0 || errorBudget > 1
            ) {
                throw new MetricsException("Invalid SLO policy.");
            }

            if (Math.abs(errorBudget - (1 - target)) > 1e-9) {
                throw new MetricsException(
                    "Error budget must equal 1 - target."
                );
            }
        }

        double remainingBudget(
            double good,
            double total
        ) {
            if (
                !Double.isFinite(good) ||
                !Double.isFinite(total) ||
                total <= 0 ||
                good < 0 ||
                good > total
            ) {
                throw new MetricsException("Invalid SLO measurements.");
            }

            double actualAvailability = good / total;
            double consumed = target - actualAvailability;

            return Math.max(
                0,
                errorBudget - Math.max(0, consumed)
            );
        }
    }

    static class MetricsRegistry {
        private final Map<String, Metric> metrics =
            new ConcurrentHashMap<>();

        <T extends Metric> T register(T metric) {
            Metric existing = metrics.putIfAbsent(
                metric.name(),
                metric
            );

            if (existing != null) {
                throw new MetricsException(
                    "Duplicate metric: " + metric.name()
                );
            }

            return metric;
        }

        Metric get(String name) {
            Metric metric = metrics.get(name);

            if (metric == null) {
                throw new MetricsException(
                    "Unknown metric: " + name
                );
            }

            return metric;
        }

        Map<String, Object> snapshot() {
            Map<String, Object> result = new TreeMap<>();

            metrics.forEach((name, metric) ->
                result.put(name, metric.snapshot())
            );

            return result;
        }
    }

    static class MonitoringService {
        private final MetricsRegistry registry =
            new MetricsRegistry();

        private final Counter requests;
        private final Gauge active;
        private final Histogram latency;

        private final SLIPolicy availability =
            new SLIPolicy("availability", 0.999);

        MonitoringService() {
            requests = registry.register(
                new Counter(
                    "http_requests_total",
                    "method",
                    "status"
                )
            );

            active = registry.register(
                new Gauge("http_active_requests")
            );

            latency = registry.register(
                new Histogram(
                    "http_request_duration_seconds",
                    new double[]{0.05, 0.1, 0.25, 0.5, 1, 2, 5},
                    "method"
                )
            );
        }

        <T> T instrument(
            String method,
            Supplier<T> operation
        ) {
            if (
                !List.of(
                    "GET", "POST", "PUT", "DELETE", "PATCH"
                ).contains(method)
            ) {
                throw new MetricsException("Unsupported HTTP method.");
            }

            Objects.requireNonNull(operation);

            active.add(1, Map.of());

            long start = System.nanoTime();
            int status = 500;

            try {
                T result = operation.get();
                status = 200;
                return result;
            } finally {
                double elapsed =
                    (System.nanoTime() - start) / 1_000_000_000.0;

                active.add(-1, Map.of());

                requests.increment(
                    1,
                    Map.of(
                        "method", method,
                        "status", String.valueOf(status)
                    )
                );

                latency.observe(
                    elapsed,
                    Map.of("method", method)
                );
            }
        }

        void report() {
            System.out.println("METRICS");

            registry.snapshot().forEach((name, values) ->
                System.out.println(name + ": " + values)
            );

            SLIResult result = availability.evaluate(
                9990,
                10000
            );

            System.out.println("\nAVAILABILITY SLI");
            System.out.println(result);

            System.out.println("\nGET P95");
            System.out.println(
                latency.percentile(
                    0.95,
                    Map.of("method", "GET")
                )
            );

            ServiceLevelObjective slo =
                new ServiceLevelObjective(
                    "availability_slo",
                    0.999,
                    0.001
                );

            System.out.println(
                "\nREMAINING ERROR BUDGET: " +
                slo.remainingBudget(9990, 10000)
            );
        }
    }

    public static void main(String[] args) {
        MonitoringService service = new MonitoringService();

        service.instrument(
            "GET",
            () -> {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new MetricsException(
                        "Request interrupted."
                    );
                }

                return "Database response";
            }
        );

        service.instrument(
            "POST",
            () -> "Resource created"
        );

        try {
            service.instrument(
                "GET",
                () -> {
                    throw new MetricsException(
                        "Simulated database failure."
                    );
                }
            );
        } catch (MetricsException error) {
            System.out.println(
                "Captured operational failure: " +
                error.getMessage()
            );
        }

        service.report();
    }
}
