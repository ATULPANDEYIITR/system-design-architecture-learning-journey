import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

public final class DistributedTransactions {

    enum ParticipantState {
        ACTIVE,
        PREPARED,
        COMMITTED,
        ABORTED
    }

    enum TransactionState {
        NEW,
        PREPARING,
        COMMIT_DECIDED,
        ABORT_DECIDED,
        COMMITTED,
        ABORTED,
        IN_DOUBT
    }

    enum Decision {
        COMMIT,
        ABORT
    }

    record Vote(String participantId, boolean yes, String reason) {}

    record JournalEvent(
        String transactionId,
        String event,
        String participantId,
        String detail
    ) {}

    static final class ProtocolException extends RuntimeException {
        ProtocolException(String message) {
            super(message);
        }
    }

    static final class ParticipantUnavailableException extends RuntimeException {
        ParticipantUnavailableException(String message) {
            super(message);
        }
    }

    static final class EventJournal {
        private final List<JournalEvent> events = new ArrayList<>();

        synchronized void append(
            String transactionId,
            String event,
            String participantId,
            String detail
        ) {
            events.add(new JournalEvent(
                transactionId, event, participantId, detail
            ));
        }

        synchronized Optional<Decision> decision(String transactionId) {
            for (int i = events.size() - 1; i >= 0; i--) {
                JournalEvent event = events.get(i);
                if (!event.transactionId().equals(transactionId)) continue;

                if (event.event().equals("GLOBAL_COMMIT")) {
                    return Optional.of(Decision.COMMIT);
                }
                if (event.event().equals("GLOBAL_ABORT")) {
                    return Optional.of(Decision.ABORT);
                }
            }
            return Optional.empty();
        }

        synchronized List<JournalEvent> eventsFor(String transactionId) {
            return events.stream()
                .filter(event -> event.transactionId().equals(transactionId))
                .toList();
        }
    }

    static final class Participant {
        private final String id;
        private long balance;
        private final EventJournal journal;
        private boolean available = true;

        private final Map<String, ParticipantState> states = new HashMap<>();
        private final Map<String, Long> reservations = new HashMap<>();
        private final Map<String, String> operationIds = new HashMap<>();

        Participant(String id, long openingBalance, EventJournal journal) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Participant ID is required");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("Opening balance cannot be negative");
            }

            this.id = id;
            this.balance = openingBalance;
            this.journal = Objects.requireNonNull(journal);
        }

        String id() {
            return id;
        }

        synchronized long balance() {
            return balance;
        }

        synchronized void setAvailable(boolean value) {
            available = value;
        }

        private void requireAvailable() {
            if (!available) {
                throw new ParticipantUnavailableException(
                    "Participant unavailable: " + id
                );
            }
        }

        synchronized Vote prepare(
            String transactionId,
            String operationId,
            long delta
        ) {
            requireAvailable();

            ParticipantState existing = states.get(transactionId);
            if (existing == ParticipantState.PREPARED) {
                if (!operationIds.get(transactionId).equals(operationId)) {
                    throw new ProtocolException("Conflicting retry");
                }
                return new Vote(id, true, "Already prepared");
            }

            if (existing == ParticipantState.COMMITTED) {
                return new Vote(id, true, "Already committed");
            }

            if (existing == ParticipantState.ABORTED) {
                return new Vote(id, false, "Already aborted");
            }

            long projected;
            try {
                projected = Math.addExact(balance, delta);
            } catch (ArithmeticException exception) {
                journal.append(
                    transactionId, "VOTE_NO", id, "Balance overflow"
                );
                return new Vote(id, false, "Balance overflow");
            }

            if (projected < 0) {
                journal.append(
                    transactionId, "VOTE_NO", id, "Insufficient funds"
                );
                return new Vote(id, false, "Insufficient funds");
            }

            // A production participant must persist this reservation and its
            // recovery metadata before returning a YES vote.
            reservations.put(transactionId, delta);
            operationIds.put(transactionId, operationId);
            states.put(transactionId, ParticipantState.PREPARED);

            journal.append(
                transactionId, "PREPARED", id, Long.toString(delta)
            );
            return new Vote(id, true, "Prepared");
        }

        synchronized void commit(String transactionId) {
            requireAvailable();

            ParticipantState state = states.get(transactionId);
            if (state == ParticipantState.COMMITTED) return;

            if (state != ParticipantState.PREPARED) {
                throw new ProtocolException(
                    "Commit requires PREPARED state for " + id
                );
            }

            balance = Math.addExact(
                balance, reservations.get(transactionId)
            );
            reservations.remove(transactionId);
            states.put(transactionId, ParticipantState.COMMITTED);

            journal.append(
                transactionId,
                "PARTICIPANT_COMMIT",
                id,
                Long.toString(balance)
            );
        }

        synchronized void abort(String transactionId) {
            requireAvailable();

            ParticipantState state = states.get(transactionId);
            if (state == ParticipantState.ABORTED) return;

            if (state == ParticipantState.COMMITTED) {
                throw new ProtocolException("Cannot abort committed work");
            }

            reservations.remove(transactionId);
            states.put(transactionId, ParticipantState.ABORTED);
            journal.append(transactionId, "PARTICIPANT_ABORT", id, "");
        }

        synchronized void applyDecision(String transactionId, Decision decision) {
            if (decision == Decision.COMMIT) {
                commit(transactionId);
            } else {
                abort(transactionId);
            }
        }
    }

    static final class Transaction {
        private final String id;
        private final String operationId;
        private final List<String> participantIds;
        private final Map<String, Boolean> votes = new LinkedHashMap<>();

        private TransactionState state = TransactionState.NEW;
        private Decision decision;

        Transaction(String id, String operationId, List<String> participantIds) {
            this.id = id;
            this.operationId = operationId;
            this.participantIds = List.copyOf(participantIds);
        }

        String id() {
            return id;
        }

        TransactionState state() {
            return state;
        }

        Map<String, Boolean> votes() {
            return Collections.unmodifiableMap(votes);
        }
    }

    static final class TransactionService {
        private final EventJournal journal;
        private final Map<String, Participant> participants = new LinkedHashMap<>();
        private final Map<String, Transaction> transactions = new HashMap<>();

        TransactionService(EventJournal journal) {
            this.journal = Objects.requireNonNull(journal);
        }

        void register(Participant participant) {
            if (participants.putIfAbsent(participant.id(), participant) != null) {
                throw new IllegalArgumentException("Duplicate participant ID");
            }
        }

        Transaction execute(Map<String, Long> deltas) {
            if (deltas.isEmpty()) {
                throw new IllegalArgumentException("No participants supplied");
            }

            for (String id : deltas.keySet()) {
                if (!participants.containsKey(id)) {
                    throw new IllegalArgumentException("Unknown participant: " + id);
                }
            }

            String transactionId = UUID.randomUUID().toString();
            String operationId = UUID.randomUUID().toString();

            Transaction transaction = new Transaction(
                transactionId,
                operationId,
                new ArrayList<>(deltas.keySet())
            );
            transactions.put(transactionId, transaction);

            journal.append(transactionId, "BEGIN", "", operationId);
            transaction.state = TransactionState.PREPARING;
            journal.append(transactionId, "PREPARING", "", "");

            boolean allYes = true;

            for (Map.Entry<String, Long> entry : deltas.entrySet()) {
                String id = entry.getKey();
                Participant participant = participants.get(id);

                try {
                    Vote vote = participant.prepare(
                        transactionId, operationId, entry.getValue()
                    );
                    transaction.votes.put(id, vote.yes());

                    journal.append(
                        transactionId,
                        "VOTE",
                        id,
                        vote.yes() ? "YES" : vote.reason()
                    );

                    if (!vote.yes()) {
                        allYes = false;
                        break;
                    }
                } catch (ParticipantUnavailableException exception) {
                    transaction.votes.put(id, false);
                    allYes = false;
                    journal.append(
                        transactionId,
                        "VOTE_UNAVAILABLE",
                        id,
                        exception.getMessage()
                    );
                    break;
                }
            }

            if (allYes && transaction.votes.size() == deltas.size()) {
                // Global commit is recorded before participants receive commit.
                journal.append(transactionId, "GLOBAL_COMMIT", "", "");
                transaction.decision = Decision.COMMIT;
                transaction.state = TransactionState.COMMIT_DECIDED;
            } else {
                journal.append(
                    transactionId, "GLOBAL_ABORT", "", "Vote failed"
                );
                transaction.decision = Decision.ABORT;
                transaction.state = TransactionState.ABORT_DECIDED;
            }

            boolean deliveryFailed = false;

            for (String participantId : transaction.participantIds) {
                try {
                    participants.get(participantId).applyDecision(
                        transactionId, transaction.decision
                    );
                } catch (ParticipantUnavailableException exception) {
                    deliveryFailed = true;
                    journal.append(
                        transactionId,
                        "DECISION_DELIVERY_FAILED",
                        participantId,
                        exception.getMessage()
                    );
                }
            }

            if (deliveryFailed) {
                transaction.state = TransactionState.IN_DOUBT;
            } else {
                transaction.state = transaction.decision == Decision.COMMIT
                    ? TransactionState.COMMITTED
                    : TransactionState.ABORTED;

                journal.append(
                    transactionId,
                    "TRANSACTION_COMPLETE",
                    "",
                    transaction.state.name()
                );
            }

            return transaction;
        }

        TransactionState recover(String transactionId) {
            Transaction transaction = transactions.get(transactionId);
            if (transaction == null) {
                throw new IllegalArgumentException("Unknown transaction");
            }

            Decision decision = journal.decision(transactionId).orElse(null);
            if (decision == null) {
                transaction.state = TransactionState.IN_DOUBT;
                return transaction.state;
            }

            for (String participantId : transaction.participantIds) {
                participants.get(participantId).applyDecision(
                    transactionId, decision
                );
            }

            transaction.decision = decision;
            transaction.state = decision == Decision.COMMIT
                ? TransactionState.COMMITTED
                : TransactionState.ABORTED;

            journal.append(transactionId, "RECOVERY_COMPLETE", "", decision.name());
            return transaction.state;
        }
    }

    private static void successfulTransfer() {
        System.out.println("\n=== Enterprise payment settlement ===");

        EventJournal journal = new EventJournal();
        TransactionService service = new TransactionService(journal);

        Participant customer = new Participant("customer", 900, journal);
        Participant merchant = new Participant("merchant", 100, journal);
        Participant feeAccount = new Participant("fee-account", 0, journal);

        service.register(customer);
        service.register(merchant);
        service.register(feeAccount);

        Map<String, Long> changes = new LinkedHashMap<>();
        changes.put("customer", -200L);
        changes.put("merchant", 190L);
        changes.put("fee-account", 10L);

        Transaction transaction = service.execute(changes);

        System.out.println("State: " + transaction.state());
        System.out.println("Votes: " + transaction.votes());
        System.out.println("Customer: " + customer.balance());
        System.out.println("Merchant: " + merchant.balance());
        System.out.println("Fee account: " + feeAccount.balance());

        if (transaction.state() != TransactionState.COMMITTED) {
            throw new IllegalStateException("Settlement did not commit");
        }

        if (customer.balance() + merchant.balance() + feeAccount.balance() != 1000) {
            throw new IllegalStateException("Balance conservation violated");
        }
    }

    private static void abortAndRecovery() {
        System.out.println("\n=== Abort delivery and recovery ===");

        EventJournal journal = new EventJournal();
        TransactionService service = new TransactionService(journal);

        Participant inventory = new Participant("inventory", 30, journal);
        Participant dispatch = new Participant("dispatch", 0, journal);

        service.register(inventory);
        service.register(dispatch);

        dispatch.setAvailable(false);

        Map<String, Long> changes = new LinkedHashMap<>();
        changes.put("inventory", -3L);
        changes.put("dispatch", 3L);

        Transaction transaction = service.execute(changes);
        System.out.println("Initial state: " + transaction.state());

        if (transaction.state() != TransactionState.IN_DOUBT) {
            throw new IllegalStateException("Expected incomplete decision delivery");
        }

        dispatch.setAvailable(true);
        TransactionState recovered = service.recover(transaction.id());

        System.out.println("Recovered state: " + recovered);
        System.out.println("Inventory balance: " + inventory.balance());
        System.out.println("Dispatch balance: " + dispatch.balance());

        if (recovered != TransactionState.ABORTED ||
            inventory.balance() != 30 || dispatch.balance() != 0) {
            throw new IllegalStateException("Recovery invariant violated");
        }
    }

    public static void main(String[] args) {
        successfulTransfer();
        abortAndRecovery();
        System.out.println("\nAll distributed transaction checks passed.");
    }
}
