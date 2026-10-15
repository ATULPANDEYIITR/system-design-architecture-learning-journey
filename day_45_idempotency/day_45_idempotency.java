import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/*
 * Enterprise-oriented idempotency model.
 *
 * The domain is a subscription provisioning API. A client may retry a
 * provisioning request when the HTTP response is lost. The service therefore
 * needs to distinguish:
 *
 *   - a new logical provisioning request
 *   - a retry of an already completed request
 *   - an attempt to reuse a key for different parameters
 *   - a request whose first execution is still active
 *
 * Java 17 is sufficient.
 */

public class IdempotencyEnterpriseDemo {

    enum RequestState {
        PROCESSING,
        COMPLETED
    }

    enum ProvisioningState {
        CREATED,
        ACTIVATED,
        FAILED
    }

    record ProvisioningRequest(
            String customerId,
            String planCode,
            int seats
    ) {
        ProvisioningRequest {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId is required");
            }

            if (planCode == null || planCode.isBlank()) {
                throw new IllegalArgumentException("planCode is required");
            }

            if (seats < 1 || seats > 1000) {
                throw new IllegalArgumentException(
                        "seats must be between 1 and 1000"
                );
            }
        }
    }

    record ProvisioningResult(
            String subscriptionId,
            String customerId,
            String planCode,
            int seats,
            ProvisioningState state,
            Instant createdAt
    ) {
    }

    record StoredResponse(
            int statusCode,
            ProvisioningResult result
    ) {
    }

    static final class IdempotencyConflictException extends RuntimeException {
        IdempotencyConflictException(String message) {
            super(message);
        }
    }

    static final class RequestInProgressException extends RuntimeException {
        RequestInProgressException(String message) {
            super(message);
        }
    }

    static final class IdempotencyRecord {
        private final String fingerprint;
        private RequestState state;
        private StoredResponse response;

        IdempotencyRecord(String fingerprint) {
            this.fingerprint = fingerprint;
            this.state = RequestState.PROCESSING;
        }

        String fingerprint() {
            return fingerprint;
        }

        RequestState state() {
            return state;
        }

        StoredResponse response() {
            return response;
        }

        void complete(StoredResponse response) {
            this.response = Objects.requireNonNull(response);
            this.state = RequestState.COMPLETED;
        }
    }

    static final class IdempotencyRepository {
        private final ConcurrentMap<String, IdempotencyRecord> records =
                new ConcurrentHashMap<>();

        /*
         * compute() performs the check-and-create decision as one map
         * operation. The value returned from the method tells the service
         * whether it owns execution or must replay/reject the request.
         */
        synchronized Claim claim(String key, String fingerprint) {
            IdempotencyRecord existing = records.get(key);

            if (existing == null) {
                IdempotencyRecord created =
                        new IdempotencyRecord(fingerprint);
                records.put(key, created);
                return new Claim.Execution(created);
            }

            if (!existing.fingerprint().equals(fingerprint)) {
                throw new IdempotencyConflictException(
                        "The idempotency key is already bound to another request."
                );
            }

            if (existing.state() == RequestState.PROCESSING) {
                throw new RequestInProgressException(
                        "The logical request is already being processed."
                );
            }

            return new Claim.Replay(existing.response());
        }

        synchronized void complete(
                String key,
                StoredResponse response
        ) {
            IdempotencyRecord record = records.get(key);

            if (record == null) {
                throw new IllegalStateException(
                        "Cannot complete a missing idempotency record."
                );
            }

            record.complete(response);
        }

        synchronized void removeProcessingRecord(String key) {
            IdempotencyRecord record = records.get(key);

            if (record != null &&
                    record.state() == RequestState.PROCESSING) {
                records.remove(key);
            }
        }

        int size() {
            return records.size();
        }
    }

    sealed interface Claim
            permits Claim.Execution, Claim.Replay {

        record Execution(IdempotencyRecord record)
                implements Claim {
        }

        record Replay(StoredResponse response)
                implements Claim {
        }
    }

    static final class SubscriptionService {
        private final ConcurrentMap<String, ProvisioningResult> subscriptions =
                new ConcurrentHashMap<>();

        ProvisioningResult provision(ProvisioningRequest request) {
            String subscriptionId =
                    "sub-" + UUID.randomUUID().toString().substring(0, 12);

            ProvisioningResult result =
                    new ProvisioningResult(
                            subscriptionId,
                            request.customerId(),
                            request.planCode(),
                            request.seats(),
                            ProvisioningState.ACTIVATED,
                            Instant.now()
                    );

            subscriptions.put(subscriptionId, result);

            return result;
        }

        int subscriptionCount() {
            return subscriptions.size();
        }

        List<ProvisioningResult> allSubscriptions() {
            return Collections.unmodifiableList(
                    new ArrayList<>(subscriptions.values())
            );
        }
    }

    static final class ProvisioningService {
        private final IdempotencyRepository idempotencyRepository;
        private final SubscriptionService subscriptionService;

        ProvisioningService(
                IdempotencyRepository idempotencyRepository,
                SubscriptionService subscriptionService
        ) {
            this.idempotencyRepository = idempotencyRepository;
            this.subscriptionService = subscriptionService;
        }

        StoredResponse provision(
                String idempotencyKey,
                ProvisioningRequest request,
                boolean simulateLostResponse
        ) {
            if (idempotencyKey == null ||
                    idempotencyKey.isBlank() ||
                    idempotencyKey.length() > 255) {
                throw new IllegalArgumentException(
                        "A valid idempotency key is required."
                );
            }

            String fingerprint = fingerprint(request);

            Claim claim = idempotencyRepository.claim(
                    idempotencyKey,
                    fingerprint
            );

            if (claim instanceof Claim.Replay replay) {
                /*
                 * The same response semantics are returned without invoking
                 * the subscription service a second time.
                 */
                return replay.response();
            }

            try {
                ProvisioningResult result =
                        subscriptionService.provision(request);

                StoredResponse response =
                        new StoredResponse(201, result);

                /*
                 * Production systems should make the business mutation and
                 * the idempotency record part of one durable transaction or
                 * use an equivalent consistency strategy.
                 */
                idempotencyRepository.complete(
                        idempotencyKey,
                        response
                );

                if (simulateLostResponse) {
                    throw new ResponseLostException(
                            "The subscription was created but the response "
                                    + "did not reach the caller."
                    );
                }

                return response;
            } catch (ResponseLostException exception) {
                /*
                 * The record is already COMPLETED. It must remain available
                 * so the retry can recover the original result.
                 */
                throw exception;
            } catch (RuntimeException exception) {
                /*
                 * This removal is appropriate only because this demonstration
                 * knows that the failure occurred before completion. A real
                 * service must not erase a key when a side effect may already
                 * have been committed.
                 */
                idempotencyRepository.removeProcessingRecord(
                        idempotencyKey
                );
                throw exception;
            }
        }

        private String fingerprint(ProvisioningRequest request) {
            return request.customerId()
                    + "|"
                    + request.planCode()
                    + "|"
                    + request.seats();
        }
    }

    static final class ResponseLostException extends RuntimeException {
        ResponseLostException(String message) {
            super(message);
        }
    }

    private static void basicRetryDemo() {
        System.out.println("\n=== Enterprise provisioning retry ===");

        IdempotencyRepository repository =
                new IdempotencyRepository();

        SubscriptionService subscriptions =
                new SubscriptionService();

        ProvisioningService service =
                new ProvisioningService(repository, subscriptions);

        ProvisioningRequest request =
                new ProvisioningRequest(
                        "customer-900",
                        "enterprise-standard",
                        25
                );

        StoredResponse first =
                service.provision(
                        "provision-001",
                        request,
                        false
                );

        StoredResponse retry =
                service.provision(
                        "provision-001",
                        request,
                        false
                );

        System.out.println("First subscription: "
                + first.result().subscriptionId());

        System.out.println("Retry subscription: "
                + retry.result().subscriptionId());

        System.out.println("Subscriptions created: "
                + subscriptions.subscriptionCount());

        System.out.println("Idempotency records: "
                + repository.size());
    }

    private static void conflictDemo() {
        System.out.println("\n=== Conflicting key reuse ===");

        IdempotencyRepository repository =
                new IdempotencyRepository();

        SubscriptionService subscriptions =
                new SubscriptionService();

        ProvisioningService service =
                new ProvisioningService(
                        repository,
                        subscriptions
                );

        service.provision(
                "provision-002",
                new ProvisioningRequest(
                        "customer-901",
                        "enterprise-standard",
                        10
                ),
                false
        );

        try {
            service.provision(
                    "provision-002",
                    new ProvisioningRequest(
                            "customer-901",
                            "enterprise-premium",
                            10
                    ),
                    false
            );
        } catch (IdempotencyConflictException exception) {
            System.out.println(
                    "Conflict rejected: "
                            + exception.getMessage()
            );
        }

        System.out.println(
                "Subscriptions created: "
                        + subscriptions.subscriptionCount()
        );
    }

    private static void lostResponseDemo() {
        System.out.println("\n=== Lost response recovery ===");

        IdempotencyRepository repository =
                new IdempotencyRepository();

        SubscriptionService subscriptions =
                new SubscriptionService();

        ProvisioningService service =
                new ProvisioningService(
                        repository,
                        subscriptions
                );

        ProvisioningRequest request =
                new ProvisioningRequest(
                        "customer-902",
                        "enterprise-premium",
                        50
                );

        try {
            service.provision(
                    "provision-003",
                    request,
                    true
            );
        } catch (ResponseLostException exception) {
            System.out.println(
                    "Caller observed: "
                            + exception.getMessage()
            );
        }

        StoredResponse recovered =
                service.provision(
                        "provision-003",
                        request,
                        false
                );

        System.out.println(
                "Recovered subscription: "
                        + recovered.result().subscriptionId()
        );

        System.out.println(
                "Subscriptions created: "
                        + subscriptions.subscriptionCount()
        );
    }

    private static void stateModelDemo() {
        System.out.println("\n=== Explicit state model ===");

        Map<ProvisioningState, String> stateMeaning =
                new EnumMap<>(ProvisioningState.class);

        stateMeaning.put(
                ProvisioningState.CREATED,
                "The subscription record exists but activation is not complete."
        );

        stateMeaning.put(
                ProvisioningState.ACTIVATED,
                "The requested subscription is active."
        );

        stateMeaning.put(
                ProvisioningState.FAILED,
                "Provisioning failed and should not be treated as successful."
        );

        stateMeaning.forEach(
                (state, description) ->
                        System.out.println(
                                state + ": " + description
                        )
        );
    }

    public static void main(String[] args) {
        basicRetryDemo();
        conflictDemo();
        lostResponseDemo();
        stateModelDemo();
    }
}
