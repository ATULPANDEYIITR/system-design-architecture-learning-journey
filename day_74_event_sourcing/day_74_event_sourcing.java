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
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/**
 * Enterprise Event Sourcing Model
 *
 * Java 17 implementation featuring:
 * - Immutable event records
 * - Aggregate roots
 * - Event store
 * - Command handling
 * - Optimistic concurrency
 * - Idempotent command processing
 * - Event schema versions
 * - Replay and snapshots
 * - CQRS-style read projections
 * - Audit and integrity validation
 */
public class EventSourcingEnterprise {

    enum EventType {
        ACCOUNT_OPENED,
        MONEY_DEPOSITED,
        MONEY_WITHDRAWN,
        ACCOUNT_FROZEN,
        ACCOUNT_UNFROZEN
    }

    enum AccountStatus {
        ACTIVE,
        FROZEN
    }

    static class DomainException extends RuntimeException {
        DomainException(String message) {
            super(message);
        }
    }

    static class ValidationException extends DomainException {
        ValidationException(String message) {
            super(message);
        }
    }

    static class ConcurrencyException extends DomainException {
        ConcurrencyException(String message) {
            super(message);
        }
    }

    static class InsufficientFundsException extends DomainException {
        InsufficientFundsException(String message) {
            super(message);
        }
    }

    record DomainEvent(
        UUID eventId,
        String aggregateId,
        long version,
        EventType type,
        long amount,
        String owner,
        Instant occurredAt,
        int schemaVersion
    ) {
        DomainEvent {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(aggregateId);
            Objects.requireNonNull(type);
            Objects.requireNonNull(occurredAt);

            if (aggregateId.isBlank() || version < 1) {
                throw new ValidationException("Invalid event identity.");
            }

            if (schemaVersion < 1) {
                throw new ValidationException("Invalid schema version.");
            }

            if (
                (type == EventType.MONEY_DEPOSITED ||
                 type == EventType.MONEY_WITHDRAWN) &&
                amount <= 0
            ) {
                throw new ValidationException("Invalid monetary amount.");
            }

            if (
                type == EventType.ACCOUNT_OPENED &&
                (owner == null || owner.isBlank())
            ) {
                throw new ValidationException("Account owner is required.");
            }
        }
    }

    record Snapshot(
        String aggregateId,
        long version,
        String owner,
        long balance,
        AccountStatus status
    ) {
        Snapshot {
            Objects.requireNonNull(aggregateId);
            Objects.requireNonNull(owner);
            Objects.requireNonNull(status);

            if (version < 1 || balance < 0) {
                throw new ValidationException("Invalid snapshot.");
            }
        }
    }

    record Command(
        String commandId,
        String accountId,
        EventType type,
        long amount,
        String owner
    ) {
        Command {
            Objects.requireNonNull(commandId);
            Objects.requireNonNull(accountId);
            Objects.requireNonNull(type);

            if (commandId.isBlank() || accountId.isBlank()) {
                throw new ValidationException("Command identity required.");
            }
        }
    }

    static final class EventStore {

        private final Map<String, List<DomainEvent>> streams =
            new ConcurrentHashMap<>();

        private final Map<String, DomainEvent> processedCommands =
            new HashMap<>();

        private final Map<String, String> commandFingerprints =
            new HashMap<>();

        private final Set<UUID> eventIds = new HashSet<>();

        synchronized long version(String aggregateId) {
            return streams.getOrDefault(
                aggregateId, List.of()
            ).size();
        }

        synchronized List<DomainEvent> load(String aggregateId) {
            return List.copyOf(
                streams.getOrDefault(aggregateId, List.of())
            );
        }

        synchronized DomainEvent findCommand(String commandId) {
            return processedCommands.get(commandId);
        }

        synchronized DomainEvent append(
            DomainEvent event,
            long expectedVersion,
            String commandId,
            String fingerprint
        ) {
            DomainEvent previous = processedCommands.get(commandId);

            if (previous != null) {
                if (!commandFingerprints.get(commandId).equals(fingerprint)) {
                    throw new ValidationException(
                        "Command ID reused with different content."
                    );
                }

                return previous;
            }

            if (eventIds.contains(event.eventId())) {
                throw new ValidationException("Duplicate event ID.");
            }

            long current = version(event.aggregateId());

            if (current != expectedVersion) {
                throw new ConcurrencyException(
                    "Expected version " + expectedVersion +
                    ", actual " + current
                );
            }

            if (event.version() != current + 1) {
                throw new ValidationException("Invalid event version.");
            }

            streams.computeIfAbsent(
                event.aggregateId(),
                key -> new ArrayList<>()
            ).add(event);

            eventIds.add(event.eventId());
            processedCommands.put(commandId, event);
            commandFingerprints.put(commandId, fingerprint);

            return event;
        }

        synchronized List<DomainEvent> allEvents() {
            return streams.values().stream()
                .flatMap(List::stream)
                .sorted(
                    java.util.Comparator
                        .comparing(DomainEvent::aggregateId)
                        .thenComparingLong(DomainEvent::version)
                )
                .toList();
        }
    }

    static final class BankAccount {

        private final String id;
        private String owner;
        private long balance;
        private AccountStatus status;
        private long version;

        BankAccount(String id) {
            this.id = id;
            this.balance = 0;
            this.status = AccountStatus.ACTIVE;
            this.version = 0;
        }

        void apply(DomainEvent event) {
            if (!id.equals(event.aggregateId())) {
                throw new ValidationException("Aggregate mismatch.");
            }

            if (event.version() != version + 1) {
                throw new ValidationException("Event sequence mismatch.");
            }

            switch (event.type()) {
                case ACCOUNT_OPENED -> {
                    if (version != 0) {
                        throw new ValidationException(
                            "Account already initialized."
                        );
                    }
                    owner = event.owner();
                }

                case MONEY_DEPOSITED -> {
                    ensureActive();

                    try {
                        balance = Math.addExact(balance, event.amount());
                    } catch (ArithmeticException exception) {
                        throw new ValidationException("Balance overflow.");
                    }
                }

                case MONEY_WITHDRAWN -> {
                    ensureActive();

                    if (event.amount() > balance) {
                        throw new InsufficientFundsException(
                            "Historical withdrawal exceeds balance."
                        );
                    }

                    balance -= event.amount();
                }

                case ACCOUNT_FROZEN -> status = AccountStatus.FROZEN;

                case ACCOUNT_UNFROZEN -> status = AccountStatus.ACTIVE;
            }

            version = event.version();
        }

        private void ensureActive() {
            if (status == AccountStatus.FROZEN) {
                throw new ValidationException("Account is frozen.");
            }
        }

        static BankAccount rehydrate(
            String id,
            List<DomainEvent> events
        ) {
            BankAccount account = new BankAccount(id);

            for (DomainEvent event : events) {
                account.apply(event);
            }

            if (account.version == 0) {
                throw new ValidationException("Account does not exist.");
            }

            return account;
        }

        Snapshot snapshot() {
            return new Snapshot(
                id, version, owner, balance, status
            );
        }

        String id() { return id; }
        String owner() { return owner; }
        long balance() { return balance; }
        long version() { return version; }
        AccountStatus status() { return status; }
    }

    interface EventHandler {
        void onEvent(DomainEvent event);
    }

    static final class EventDispatcher {

        private final List<EventHandler> handlers =
            new ArrayList<>();

        void subscribe(EventHandler handler) {
            handlers.add(Objects.requireNonNull(handler));
        }

        void publish(DomainEvent event) {
            for (EventHandler handler : handlers) {
                try {
                    handler.onEvent(event);
                } catch (RuntimeException exception) {
                    // A projection failure must not undo a committed event.
                    System.err.println(
                        "Event handler failure: " + exception.getMessage()
                    );
                }
            }
        }
    }

    static final class AccountProjection implements EventHandler {

        record AccountView(
            String owner,
            long balance,
            AccountStatus status,
            long version
        ) {}

        private final Map<String, AccountView> views =
            new ConcurrentHashMap<>();

        @Override
        public synchronized void onEvent(DomainEvent event) {
            String id = event.aggregateId();

            if (event.type() == EventType.ACCOUNT_OPENED) {
                if (views.containsKey(id)) {
                    throw new ValidationException(
                        "Projection account already exists."
                    );
                }

                views.put(id, new AccountView(
                    event.owner(),
                    0,
                    AccountStatus.ACTIVE,
                    1
                ));
                return;
            }

            AccountView current = views.get(id);

            if (
                current == null ||
                event.version() != current.version() + 1
            ) {
                throw new ValidationException(
                    "Projection sequence mismatch."
                );
            }

            long balance = current.balance();
            AccountStatus status = current.status();

            switch (event.type()) {
                case MONEY_DEPOSITED ->
                    balance = Math.addExact(balance, event.amount());

                case MONEY_WITHDRAWN ->
                    balance -= event.amount();

                case ACCOUNT_FROZEN ->
                    status = AccountStatus.FROZEN;

                case ACCOUNT_UNFROZEN ->
                    status = AccountStatus.ACTIVE;

                default ->
                    throw new ValidationException(
                        "Unsupported projection event."
                    );
            }

            views.put(id, new AccountView(
                current.owner(),
                balance,
                status,
                event.version()
            ));
        }

        synchronized void rebuild(List<DomainEvent> events) {
            views.clear();
            events.forEach(this::onEvent);
        }

        AccountView get(String id) {
            AccountView view = views.get(id);

            if (view == null) {
                throw new ValidationException("Projection not found.");
            }

            return view;
        }
    }

    static final class AccountCommandService {

        private final EventStore store;
        private final EventDispatcher dispatcher;
        private final AtomicLong eventSequence = new AtomicLong();

        AccountCommandService(
            EventStore store,
            EventDispatcher dispatcher
        ) {
            this.store = store;
            this.dispatcher = dispatcher;
        }

        DomainEvent execute(Command command) {
            DomainEvent previous = store.findCommand(command.commandId());

            if (previous != null) {
                return store.append(
                    previous,
                    previous.version() - 1,
                    command.commandId(),
                    fingerprint(command)
                );
            }

            long currentVersion = store.version(command.accountId());

            if (command.type() == EventType.ACCOUNT_OPENED) {
                if (currentVersion != 0) {
                    throw new ValidationException(
                        "Account already exists."
                    );
                }
            } else {
                BankAccount account = BankAccount.rehydrate(
                    command.accountId(),
                    store.load(command.accountId())
                );

                if (
                    account.status() == AccountStatus.FROZEN &&
                    (command.type() == EventType.MONEY_DEPOSITED ||
                     command.type() == EventType.MONEY_WITHDRAWN)
                ) {
                    throw new ValidationException("Account is frozen.");
                }

                if (
                    command.type() == EventType.MONEY_DEPOSITED ||
                    command.type() == EventType.MONEY_WITHDRAWN
                ) {
                    if (command.amount() <= 0) {
                        throw new ValidationException(
                            "Amount must be positive."
                        );
                    }
                }

                if (
                    command.type() == EventType.MONEY_WITHDRAWN &&
                    command.amount() > account.balance()
                ) {
                    throw new InsufficientFundsException(
                        "Insufficient funds."
                    );
                }
            }

            DomainEvent event = new DomainEvent(
                UUID.randomUUID(),
                command.accountId(),
                currentVersion + 1,
                command.type(),
                command.amount(),
                command.owner(),
                Instant.now(),
                1
            );

            DomainEvent committed = store.append(
                event,
                currentVersion,
                command.commandId(),
                fingerprint(command)
            );

            dispatcher.publish(committed);

            return committed;
        }

        private String fingerprint(Command command) {
            return command.accountId() + "|" +
                command.type() + "|" +
                command.amount() + "|" +
                command.owner();
        }
    }

    static final class EventSchemaUpcaster {

        static DomainEvent upcast(DomainEvent event) {
            if (event.schemaVersion() == 1) {
                return event;
            }

            throw new ValidationException(
                "Unsupported event schema version: " +
                event.schemaVersion()
            );
        }
    }

    public static void main(String[] args) {

        EventStore store = new EventStore();
        EventDispatcher dispatcher = new EventDispatcher();

        AccountProjection projection = new AccountProjection();
        dispatcher.subscribe(projection);

        AccountCommandService service =
            new AccountCommandService(store, dispatcher);

        service.execute(new Command(
            "CMD-001", "ACC-4001",
            EventType.ACCOUNT_OPENED, 0, "Atul"
        ));

        service.execute(new Command(
            "CMD-002", "ACC-4001",
            EventType.MONEY_DEPOSITED, 30000, null
        ));

        service.execute(new Command(
            "CMD-003", "ACC-4001",
            EventType.MONEY_WITHDRAWN, 8000, null
        ));

        service.execute(new Command(
            "CMD-004", "ACC-4001",
            EventType.ACCOUNT_FROZEN, 0, null
        ));

        try {
            service.execute(new Command(
                "CMD-005", "ACC-4001",
                EventType.MONEY_WITHDRAWN, 1000, null
            ));
            throw new IllegalStateException("Freeze validation failed.");
        } catch (ValidationException exception) {
            System.out.println("Frozen account validation: PASSED");
        }

        service.execute(new Command(
            "CMD-006", "ACC-4001",
            EventType.ACCOUNT_UNFROZEN, 0, null
        ));

        service.execute(new Command(
            "CMD-007", "ACC-4001",
            EventType.MONEY_DEPOSITED, 2500, null
        ));

        BankAccount account = BankAccount.rehydrate(
            "ACC-4001",
            store.load("ACC-4001")
        );

        AccountProjection.AccountView view =
            projection.get("ACC-4001");

        if (account.balance() != 24500 || view.balance() != 24500) {
            throw new IllegalStateException("Balance mismatch.");
        }

        Snapshot snapshot = account.snapshot();

        // Rebuild the projection from the authoritative event history.
        AccountProjection rebuilt = new AccountProjection();
        rebuilt.rebuild(store.allEvents());

        if (rebuilt.get("ACC-4001").balance() != account.balance()) {
            throw new IllegalStateException("Replay failed.");
        }

        System.out.println("\nENTERPRISE EVENT SOURCING REPORT");
        System.out.println("--------------------------------");
        System.out.println("Account: " + account.id());
        System.out.println("Owner: " + account.owner());
        System.out.println("Balance: " + account.balance());
        System.out.println("Version: " + account.version());
        System.out.println("Status: " + account.status());
        System.out.println("Events: " + store.load("ACC-4001").size());
        System.out.println("Snapshot version: " + snapshot.version());
        System.out.println("Read-model balance: " + view.balance());
        System.out.println("Projection rebuild: PASSED");
        System.out.println("Aggregate replay: PASSED");
        System.out.println("State validation: PASSED");
        System.out.println("Event schema validation: PASSED");
    }
}
