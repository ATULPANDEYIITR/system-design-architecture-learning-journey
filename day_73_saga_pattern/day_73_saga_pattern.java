import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

/**
 * Saga Pattern: Enterprise Distributed Transaction Management.
 *
 * Java 17
 *
 * Demonstrates:
 * - Explicit transaction state transitions
 * - Service-oriented architecture
 * - Forward actions and compensations
 * - Retry policies
 * - Idempotency
 * - Execution auditing
 * - Failure recovery
 */

public class SagaPattern {

    enum SagaStatus {
        PENDING,
        RUNNING,
        COMPENSATING,
        COMPLETED,
        COMPENSATED,
        FAILED
    }

    enum StepStatus {
        PENDING,
        COMPLETED,
        COMPENSATED,
        FAILED
    }

    record Order(
        String orderId,
        double amount,
        String customerId
    ) {
        Order {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("Order ID required");
            }

            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("Customer ID required");
            }

            if (!Double.isFinite(amount) || amount <= 0) {
                throw new IllegalArgumentException("Invalid order amount");
            }
        }
    }

    record AuditEvent(
        Instant timestamp,
        String event,
        String details
    ) {}

    static class SagaException extends RuntimeException {
        SagaException(String message) {
            super(message);
        }

        SagaException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    @FunctionalInterface
    interface TransactionAction {
        void execute() throws Exception;
    }

    static class RetryPolicy {
        private final int maxAttempts;

        RetryPolicy(int maxAttempts) {
            if (maxAttempts < 1 || maxAttempts > 10) {
                throw new IllegalArgumentException(
                    "Retry attempts must be between 1 and 10"
                );
            }

            this.maxAttempts = maxAttempts;
        }

        void execute(TransactionAction action) {
            Exception lastError = null;

            for (int attempt = 1; attempt <= maxAttempts; attempt++) {
                try {
                    action.execute();
                    return;

                } catch (Exception error) {
                    lastError = error;

                    if (attempt < maxAttempts) {
                        try {
                            Thread.sleep(Math.min(
                                50L * (1L << (attempt - 1)),
                                1000L
                            ));
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                            throw new SagaException(
                                "Retry interrupted",
                                interrupted
                            );
                        }
                    }
                }
            }

            throw new SagaException(
                "Operation failed after retries",
                lastError
            );
        }
    }

    static class SagaStep {
        private final String name;
        private final TransactionAction action;
        private final TransactionAction compensation;

        private StepStatus status = StepStatus.PENDING;
        private int attempts;

        SagaStep(
            String name,
            TransactionAction action,
            TransactionAction compensation
        ) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Step name required");
            }

            this.name = name;
            this.action = Objects.requireNonNull(action);
            this.compensation = Objects.requireNonNull(compensation);
        }
    }

    static class InventoryService {
        private final Set<String> reservations = new HashSet<>();

        synchronized void reserve(String orderId) {
            reservations.add(orderId);
            System.out.println("Inventory reserved: " + orderId);
        }

        synchronized void release(String orderId) {
            reservations.remove(orderId);
            System.out.println("Inventory released: " + orderId);
        }

        synchronized boolean exists(String orderId) {
            return reservations.contains(orderId);
        }
    }

    static class PaymentService {
        private final Map<String, Double> charges = new HashMap<>();

        synchronized void charge(Order order) {
            charges.putIfAbsent(order.orderId(), order.amount());

            System.out.println(
                "Payment charged: " + order.orderId()
            );
        }

        synchronized void refund(String orderId) {
            charges.remove(orderId);
            System.out.println("Payment refunded: " + orderId);
        }

        synchronized boolean exists(String orderId) {
            return charges.containsKey(orderId);
        }
    }

    static class ShippingService {
        private final Set<String> shipments = new HashSet<>();

        synchronized void createShipment(
            String orderId,
            boolean shouldFail
        ) {
            if (shouldFail) {
                throw new SagaException(
                    "Shipping provider unavailable"
                );
            }

            shipments.add(orderId);
            System.out.println("Shipment created: " + orderId);
        }

        synchronized void cancelShipment(String orderId) {
            shipments.remove(orderId);
            System.out.println("Shipment cancelled: " + orderId);
        }

        synchronized boolean exists(String orderId) {
            return shipments.contains(orderId);
        }
    }

    static class Saga {
        private final String sagaId = UUID.randomUUID().toString();
        private final Order order;
        private final List<SagaStep> steps;

        private final List<SagaStep> completedSteps = new ArrayList<>();
        private final List<AuditEvent> history = new ArrayList<>();

        private SagaStatus status = SagaStatus.PENDING;

        Saga(Order order, List<SagaStep> steps) {
            this.order = Objects.requireNonNull(order);

            if (steps == null || steps.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one transaction step is required"
                );
            }

            this.steps = List.copyOf(steps);
        }

        void record(String event, String details) {
            history.add(new AuditEvent(
                Instant.now(),
                event,
                details
            ));

            System.out.println("[" + event + "] " + details);
        }

        String getSagaId() {
            return sagaId;
        }

        SagaStatus getStatus() {
            return status;
        }

        List<AuditEvent> getHistory() {
            return Collections.unmodifiableList(history);
        }
    }

    static class SagaOrchestrator {
        private final RetryPolicy retryPolicy;

        SagaOrchestrator(RetryPolicy retryPolicy) {
            this.retryPolicy = retryPolicy;
        }

        SagaStatus execute(Saga saga) {
            if (saga.status != SagaStatus.PENDING) {
                throw new SagaException(
                    "Saga has already been executed"
                );
            }

            saga.status = SagaStatus.RUNNING;
            saga.record("SAGA_STARTED", saga.order.orderId());

            try {
                for (SagaStep step : saga.steps) {
                    saga.record("STEP_STARTED", step.name);

                    try {
                        retryPolicy.execute(() -> {
                            step.attempts++;
                            step.action.execute();
                        });

                        step.status = StepStatus.COMPLETED;
                        saga.completedSteps.add(step);

                        saga.record(
                            "STEP_COMPLETED",
                            step.name + "; attempts=" + step.attempts
                        );

                    } catch (Exception error) {
                        step.status = StepStatus.FAILED;

                        saga.record(
                            "STEP_FAILED",
                            step.name + ": " + error.getMessage()
                        );

                        throw new SagaException(
                            "Transaction step failed",
                            error
                        );
                    }
                }

                saga.status = SagaStatus.COMPLETED;
                saga.record("SAGA_COMPLETED", saga.order.orderId());

            } catch (SagaException error) {
                saga.record(
                    "COMPENSATION_TRIGGERED",
                    error.getMessage()
                );

                compensate(saga);
            }

            return saga.status;
        }

        private void compensate(Saga saga) {
            saga.status = SagaStatus.COMPENSATING;

            boolean allCompensationsSucceeded = true;

            for (int i = saga.completedSteps.size() - 1; i >= 0; i--) {
                SagaStep step = saga.completedSteps.get(i);

                try {
                    step.compensation.execute();

                    step.status = StepStatus.COMPENSATED;

                    saga.record(
                        "STEP_COMPENSATED",
                        step.name
                    );

                } catch (Exception error) {
                    allCompensationsSucceeded = false;

                    saga.record(
                        "COMPENSATION_FAILED",
                        step.name + ": " + error.getMessage()
                    );
                }
            }

            saga.status = allCompensationsSucceeded
                ? SagaStatus.COMPENSATED
                : SagaStatus.FAILED;

            if (!allCompensationsSucceeded) {
                saga.record(
                    "MANUAL_RECOVERY_REQUIRED",
                    saga.order.orderId()
                );
            }
        }
    }

    static Saga createOrderSaga(
        Order order,
        InventoryService inventory,
        PaymentService payment,
        ShippingService shipping,
        boolean failShipping
    ) {
        return new Saga(
            order,
            List.of(
                new SagaStep(
                    "Reserve Inventory",
                    () -> inventory.reserve(order.orderId()),
                    () -> inventory.release(order.orderId())
                ),
                new SagaStep(
                    "Charge Payment",
                    () -> payment.charge(order),
                    () -> payment.refund(order.orderId())
                ),
                new SagaStep(
                    "Create Shipment",
                    () -> shipping.createShipment(
                        order.orderId(),
                        failShipping
                    ),
                    () -> shipping.cancelShipment(order.orderId())
                )
            )
        );
    }

    public static void main(String[] args) {
        InventoryService inventory = new InventoryService();
        PaymentService payment = new PaymentService();
        ShippingService shipping = new ShippingService();

        SagaOrchestrator orchestrator = new SagaOrchestrator(
            new RetryPolicy(3)
        );

        Order successfulOrder = new Order(
            "ORDER-4001",
            1800,
            "CUSTOMER-101"
        );

        Order failedOrder = new Order(
            "ORDER-4002",
            3200,
            "CUSTOMER-102"
        );

        System.out.println("\nCASE 1: Successful transaction");

        Saga successfulSaga = createOrderSaga(
            successfulOrder,
            inventory,
            payment,
            shipping,
            false
        );

        System.out.println(
            "Result: " + orchestrator.execute(successfulSaga)
        );

        System.out.println("\nCASE 2: Failed shipping transaction");

        Saga failedSaga = createOrderSaga(
            failedOrder,
            inventory,
            payment,
            shipping,
            true
        );

        System.out.println(
            "Result: " + orchestrator.execute(failedSaga)
        );

        System.out.println("\nFINAL VALIDATION");

        if (!inventory.exists("ORDER-4001")) {
            throw new AssertionError("Successful inventory missing");
        }

        if (inventory.exists("ORDER-4002")) {
            throw new AssertionError("Failed inventory not released");
        }

        if (payment.exists("ORDER-4002")) {
            throw new AssertionError("Failed payment not refunded");
        }

        if (shipping.exists("ORDER-4002")) {
            throw new AssertionError("Unexpected shipment");
        }

        System.out.println("All validation checks passed.");
    }
}
