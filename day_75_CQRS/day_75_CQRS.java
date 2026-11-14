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
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Collectors;

/*
 * CQRS: Enterprise Repository and Financial Account Platform
 *
 * Java 17
 * Standard library only.
 *
 * Separates:
 * 1. Command processing and domain invariants
 * 2. Event persistence
 * 3. Asynchronous read-model projections
 * 4. Query-oriented reporting
 * 5. Application-level idempotency
 */

// ============================================================
// 1. APPLICATION EXCEPTIONS
// ============================================================

class CQRSException extends RuntimeException {
    CQRSException(String message) {
        super(message);
    }
}

class ValidationException extends CQRSException {
    ValidationException(String message) {
        super(message);
    }
}

class NotFoundException extends CQRSException {
    NotFoundException(String message) {
        super(message);
    }
}

class ConcurrencyException extends CQRSException {
    ConcurrencyException(String message) {
        super(message);
    }
}

class InsufficientFundsException extends CQRSException {
    InsufficientFundsException(String message) {
        super(message);
    }
}

class ProjectionException extends CQRSException {
    ProjectionException(String message) {
        super(message);
    }
}

// ============================================================
// 2. DOMAIN ENUMERATIONS
// ============================================================

enum CommandType {
    CREATE_ACCOUNT,
    DEPOSIT,
    WITHDRAW
}

enum EventType {
    ACCOUNT_CREATED,
    MONEY_DEPOSITED,
    MONEY_WITHDRAWN
}

enum AccountStatus {
    ACTIVE,
    SUSPENDED,
    CLOSED
}

// ============================================================
// 3. MONEY VALUE OBJECT
// ============================================================

record Money(long cents) {

    Money {
        if (cents < 0) {
            throw new ValidationException(
                "Money cannot be negative."
            );
        }
    }

    static Money fromDouble(double value) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new ValidationException(
                "Amount must be positive and finite."
            );
        }

        long cents = Math.round(value * 100);

        if (Math.abs(value * 100 - cents) > 1e-7) {
            throw new ValidationException(
                "Only two decimal places are allowed."
            );
        }

        return new Money(cents);
    }

    Money add(Money other) {
        return new Money(Math.addExact(cents, other.cents));
    }

    Money subtract(Money other) {
        if (other.cents > cents) {
            throw new InsufficientFundsException(
                "Insufficient account balance."
            );
        }

        return new Money(cents - other.cents);
    }

    double asDouble() {
        return cents / 100.0;
    }

    @Override
    public String toString() {
        return String.format("%.2f", asDouble());
    }
}

// ============================================================
// 4. COMMAND RECORD
// ============================================================

record Command(
    String id,
    CommandType type,
    String accountId,
    Money amount,
    Integer expectedVersion
) {
    Command {
        Objects.requireNonNull(id);
        Objects.requireNonNull(type);
        Objects.requireNonNull(accountId);

        if (id.isBlank() || accountId.isBlank()) {
            throw new ValidationException(
                "Command identifiers cannot be empty."
            );
        }

        if (
            expectedVersion != null &&
            expectedVersion < 0
        ) {
            throw new ValidationException(
                "Invalid expected version."
            );
        }

        if (
            type == CommandType.DEPOSIT ||
            type == CommandType.WITHDRAW
        ) {
            Objects.requireNonNull(amount);
        }
    }

    static Command deposit(
        String accountId,
        double amount,
        int version
    ) {
        return new Command(
            UUID.randomUUID().toString(),
            CommandType.DEPOSIT,
            accountId,
            Money.fromDouble(amount),
            version
        );
    }

    static Command withdraw(
        String accountId,
        double amount,
        int version
    ) {
        return new Command(
            UUID.randomUUID().toString(),
            CommandType.WITHDRAW,
            accountId,
            Money.fromDouble(amount),
            version
        );
    }
}

// ============================================================
// 5. DOMAIN EVENT RECORD
// ============================================================

record DomainEvent(
    String id,
    EventType type,
    String aggregateId,
    int version,
    Money amount,
    String owner,
    Instant occurredAt
) {
    DomainEvent {
        Objects.requireNonNull(id);
        Objects.requireNonNull(type);
        Objects.requireNonNull(aggregateId);
        Objects.requireNonNull(occurredAt);

        if (version <= 0) {
            throw new ValidationException(
                "Event version must be positive."
            );
        }
    }

    static DomainEvent create(
        EventType type,
        String aggregateId,
        int version,
        Money amount,
        String owner
    ) {
        return new DomainEvent(
            UUID.randomUUID().toString(),
            type,
            aggregateId,
            version,
            amount,
            owner,
            Instant.now()
        );
    }
}

// ============================================================
// 6. WRITE MODEL AGGREGATE
// ============================================================

final class AccountAggregate {

    private final String accountId;
    private final String owner;

    private Money balance;
    private int version;
    private AccountStatus status;

    AccountAggregate(
        String accountId,
        String owner,
        Money balance,
        int version
    ) {
        if (
            accountId == null ||
            accountId.isBlank() ||
            owner == null ||
            owner.isBlank()
        ) {
            throw new ValidationException(
                "Account details are required."
            );
        }

        this.accountId = accountId;
        this.owner = owner;
        this.balance = balance;
        this.version = version;
        this.status = AccountStatus.ACTIVE;
    }

    DomainEvent deposit(Money amount) {
        ensureActive();

        balance = balance.add(amount);
        version++;

        return DomainEvent.create(
            EventType.MONEY_DEPOSITED,
            accountId,
            version,
            amount,
            null
        );
    }

    DomainEvent withdraw(Money amount) {
        ensureActive();

        balance = balance.subtract(amount);
        version++;

        return DomainEvent.create(
            EventType.MONEY_WITHDRAWN,
            accountId,
            version,
            amount,
            null
        );
    }

    private void ensureActive() {
        if (status != AccountStatus.ACTIVE) {
            throw new ValidationException(
                "Account is not active."
            );
        }
    }

    void rollback(DomainEvent event) {
        if (event.type() == EventType.MONEY_DEPOSITED) {
            balance = balance.subtract(event.amount());
        } else if (
            event.type() == EventType.MONEY_WITHDRAWN
        ) {
            balance = balance.add(event.amount());
        }

        version--;
    }

    String accountId() {
        return accountId;
    }

    String owner() {
        return owner;
    }

    Money balance() {
        return balance;
    }

    int version() {
        return version;
    }

    AccountStatus status() {
        return status;
    }
}

// ============================================================
// 7. EVENT STORE INTERFACE
// ============================================================

interface EventRepository {

    void append(
        String aggregateId,
        int expectedVersion,
        List<DomainEvent> events
    );

    List<DomainEvent> read(String aggregateId);

    List<DomainEvent> readAll();

    int version(String aggregateId);
}

// ============================================================
// 8. IN-MEMORY EVENT STORE
// ============================================================

final class InMemoryEventStore implements EventRepository {

    private final Map<String, List<DomainEvent>> streams =
        new HashMap<>();

    private final Set<String> eventIds =
        new HashSet<>();

    @Override
    public synchronized void append(
        String aggregateId,
        int expectedVersion,
        List<DomainEvent> events
    ) {
        if (events == null || events.isEmpty()) {
            throw new ValidationException(
                "Event batch cannot be empty."
            );
        }

        List<DomainEvent> existing = streams.getOrDefault(
            aggregateId,
            List.of()
        );

        if (existing.size() != expectedVersion) {
            throw new ConcurrencyException(
                "Optimistic concurrency conflict."
            );
        }

        int nextVersion = expectedVersion;
        Set<String> batchIds = new HashSet<>();

        for (DomainEvent event : events) {
            nextVersion++;

            if (
                !event.aggregateId().equals(aggregateId) ||
                event.version() != nextVersion ||
                eventIds.contains(event.id()) ||
                !batchIds.add(event.id())
            ) {
                throw new ValidationException(
                    "Invalid or duplicate event."
                );
            }
        }

        List<DomainEvent> updated = new ArrayList<>(existing);
        updated.addAll(events);

        // The stream is replaced only after complete validation.
        streams.put(aggregateId, updated);

        for (DomainEvent event : events) {
            eventIds.add(event.id());
        }
    }

    @Override
    public synchronized List<DomainEvent> read(
        String aggregateId
    ) {
        return List.copyOf(
            streams.getOrDefault(aggregateId, List.of())
        );
    }

    @Override
    public synchronized List<DomainEvent> readAll() {
        return streams.values()
            .stream()
            .flatMap(List::stream)
            .sorted(
                java.util.Comparator
                    .comparing(DomainEvent::aggregateId)
                    .thenComparingInt(DomainEvent::version)
            )
            .toList();
    }

    @Override
    public synchronized int version(String aggregateId) {
        return streams.getOrDefault(
            aggregateId,
            List.of()
        ).size();
    }
}

// ============================================================
// 9. IDEMPOTENCY REGISTRY
// ============================================================

final class CommandRegistry {

    private final Map<String, List<DomainEvent>> results =
        new HashMap<>();

    synchronized boolean contains(String commandId) {
        return results.containsKey(commandId);
    }

    synchronized List<DomainEvent> get(String commandId) {
        return results.get(commandId);
    }

    synchronized void save(
        String commandId,
        List<DomainEvent> events
    ) {
        results.put(commandId, List.copyOf(events));
    }
}

// ============================================================
// 10. COMMAND HANDLER
// ============================================================

final class CommandHandler {

    private final EventRepository eventStore;
    private final CommandRegistry registry;

    private final Map<String, AccountAggregate> aggregates =
        new HashMap<>();

    private final ReentrantLock lock = new ReentrantLock();

    CommandHandler(
        EventRepository eventStore,
        CommandRegistry registry
    ) {
        this.eventStore = eventStore;
        this.registry = registry;
    }

    DomainEvent createAccount(
        String commandId,
        String accountId,
        String owner
    ) {
        lock.lock();

        try {
            if (registry.contains(commandId)) {
                return registry.get(commandId).get(0);
            }

            if (aggregates.containsKey(accountId)) {
                throw new ValidationException(
                    "Account already exists."
                );
            }

            DomainEvent event = DomainEvent.create(
                EventType.ACCOUNT_CREATED,
                accountId,
                1,
                new Money(0),
                owner
            );

            eventStore.append(accountId, 0, List.of(event));

            aggregates.put(
                accountId,
                new AccountAggregate(
                    accountId,
                    owner,
                    new Money(0),
                    1
                )
            );

            registry.save(commandId, List.of(event));

            return event;

        } finally {
            lock.unlock();
        }
    }

    List<DomainEvent> handle(Command command) {
        lock.lock();

        try {
            if (registry.contains(command.id())) {
                return registry.get(command.id());
            }

            AccountAggregate aggregate = aggregates.get(
                command.accountId()
            );

            if (aggregate == null) {
                throw new NotFoundException(
                    "Account not found."
                );
            }

            int currentVersion = eventStore.version(
                command.accountId()
            );

            if (aggregate.version() != currentVersion) {
                throw new ConcurrencyException(
                    "Write-model version mismatch."
                );
            }

            if (
                command.expectedVersion() != null &&
                command.expectedVersion() != currentVersion
            ) {
                throw new ConcurrencyException(
                    "Stale command version."
                );
            }

            DomainEvent event;

            if (command.type() == CommandType.DEPOSIT) {
                event = aggregate.deposit(command.amount());

            } else if (
                command.type() == CommandType.WITHDRAW
            ) {
                event = aggregate.withdraw(command.amount());

            } else {
                throw new ValidationException(
                    "Unsupported command."
                );
            }

            try {
                eventStore.append(
                    command.accountId(),
                    currentVersion,
                    List.of(event)
                );
            } catch (RuntimeException exception) {
                aggregate.rollback(event);
                throw exception;
            }

            List<DomainEvent> result = List.of(event);

            registry.save(command.id(), result);

            return result;

        } finally {
            lock.unlock();
        }
    }
}

// ============================================================
// 11. READ MODEL RECORD
// ============================================================

record AccountView(
    String accountId,
    String owner,
    Money balance,
    int version,
    int transactionCount,
    Instant lastUpdated
) {}

// ============================================================
// 12. PROJECTION SERVICE
// ============================================================

final class AccountProjection {

    private final Map<String, AccountView> accounts =
        new HashMap<>();

    private final Set<String> processedEvents =
        new HashSet<>();

    synchronized void apply(DomainEvent event) {
        if (processedEvents.contains(event.id())) {
            return;
        }

        AccountView current = accounts.get(
            event.aggregateId()
        );

        if (event.type() == EventType.ACCOUNT_CREATED) {
            if (current != null) {
                throw new ProjectionException(
                    "Duplicate account projection."
                );
            }

            accounts.put(
                event.aggregateId(),
                new AccountView(
                    event.aggregateId(),
                    event.owner(),
                    new Money(0),
                    event.version(),
                    0,
                    event.occurredAt()
                )
            );

        } else {
            if (current == null) {
                throw new ProjectionException(
                    "Account read model is missing."
                );
            }

            if (event.version() != current.version() + 1) {
                throw new ProjectionException(
                    "Projection sequence gap."
                );
            }

            Money balance;

            if (event.type() == EventType.MONEY_DEPOSITED) {
                balance = current.balance().add(event.amount());
            } else {
                balance = current.balance().subtract(event.amount());
            }

            accounts.put(
                event.aggregateId(),
                new AccountView(
                    current.accountId(),
                    current.owner(),
                    balance,
                    event.version(),
                    current.transactionCount() + 1,
                    event.occurredAt()
                )
            );
        }

        processedEvents.add(event.id());
    }

    synchronized void rebuild(List<DomainEvent> events) {
        accounts.clear();
        processedEvents.clear();

        events.stream()
            .sorted(
                java.util.Comparator
                    .comparing(DomainEvent::aggregateId)
                    .thenComparingInt(DomainEvent::version)
            )
            .forEach(this::apply);
    }

    synchronized AccountView get(String accountId) {
        AccountView view = accounts.get(accountId);

        if (view == null) {
            throw new NotFoundException(
                "Account not found in read model."
            );
        }

        return view;
    }

    synchronized List<AccountView> all() {
        return List.copyOf(accounts.values());
    }
}

// ============================================================
// 13. QUERY SERVICE
// ============================================================

final class QueryService {

    private final AccountProjection projection;

    QueryService(AccountProjection projection) {
        this.projection = projection;
    }

    AccountView accountDetails(String accountId) {
        return projection.get(accountId);
    }

    List<AccountView> activeAccountReport() {
        return projection.all()
            .stream()
            .filter(account -> account.balance().cents() >= 0)
            .collect(Collectors.toUnmodifiableList());
    }

    double totalBalance() {
        long total = 0;

        for (AccountView account : projection.all()) {
            total = Math.addExact(
                total,
                account.balance().cents()
            );
        }

        return total / 100.0;
    }

    List<AccountView> highestBalances(int limit) {
        if (limit <= 0) {
            throw new ValidationException(
                "Limit must be positive."
            );
        }

        return projection.all()
            .stream()
            .sorted(
                java.util.Comparator.comparingLong(
                    (AccountView account) ->
                        account.balance().cents()
                ).reversed()
            )
            .limit(limit)
            .toList();
    }
}

// ============================================================
// 14. APPLICATION SERVICE
// ============================================================

final class BankingApplication {

    private final InMemoryEventStore eventStore =
        new InMemoryEventStore();

    private final CommandRegistry registry =
        new CommandRegistry();

    private final AccountProjection projection =
        new AccountProjection();

    private final CommandHandler commandHandler =
        new CommandHandler(eventStore, registry);

    private final QueryService queryService =
        new QueryService(projection);

    CommandHandler commands() {
        return commandHandler;
    }

    QueryService queries() {
        return queryService;
    }

    void synchronize() {
        for (DomainEvent event : eventStore.readAll()) {
            projection.apply(event);
        }
    }

    void rebuildProjection() {
        projection.rebuild(eventStore.readAll());
    }

    EventRepository events() {
        return eventStore;
    }
}

// ============================================================
// 15. EXECUTABLE ENTERPRISE SCENARIO
// ============================================================

public class CQRSBanking {

    private static void require(
        boolean condition,
        String message
    ) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {

        BankingApplication application =
            new BankingApplication();

        CommandHandler commands = application.commands();

        commands.createAccount(
            "CMD-001",
            "ACC-4001",
            "Priya Sharma"
        );

        commands.createAccount(
            "CMD-002",
            "ACC-4002",
            "Arjun Verma"
        );

        commands.handle(
            Command.deposit("ACC-4001", 20000, 1)
        );

        commands.handle(
            Command.deposit("ACC-4001", 5000, 2)
        );

        commands.handle(
            Command.withdraw("ACC-4001", 4000, 3)
        );

        commands.handle(
            Command.deposit("ACC-4002", 10000, 1)
        );

        // Projection synchronization is independent of writes.
        application.synchronize();

        QueryService queries = application.queries();

        AccountView first = queries.accountDetails("ACC-4001");
        AccountView second = queries.accountDetails("ACC-4002");

        require(
            first.balance().asDouble() == 21000.0,
            "First account balance incorrect."
        );

        require(
            second.balance().asDouble() == 10000.0,
            "Second account balance incorrect."
        );

        System.out.println("ACCOUNT REPORT");

        for (AccountView account : queries.activeAccountReport()) {
            System.out.println(
                account.accountId()
                + " | "
                + account.owner()
                + " | "
                + account.balance()
                + " | version="
                + account.version()
                + " | transactions="
                + account.transactionCount()
            );
        }

        System.out.println(
            "\nTotal balance: " + queries.totalBalance()
        );

        System.out.println("\nTOP ACCOUNTS");

        queries.highestBalances(2).forEach(
            account -> System.out.println(
                account.accountId()
                + " : "
                + account.balance()
            )
        );

        // Insufficient funds validation.
        try {
            commands.handle(
                Command.withdraw("ACC-4001", 999999, 4)
            );

            throw new AssertionError(
                "Insufficient funds should be rejected."
            );

        } catch (InsufficientFundsException exception) {
            System.out.println(
                "\nInsufficient funds rejected."
            );
        }

        // Optimistic concurrency validation.
        try {
            commands.handle(
                Command.deposit("ACC-4001", 100, 1)
            );

            throw new AssertionError(
                "Stale command should be rejected."
            );

        } catch (ConcurrencyException exception) {
            System.out.println("Stale command rejected.");
        }

        // Replay projection.
        double original = queries.totalBalance();

        application.rebuildProjection();

        double rebuilt = queries.totalBalance();

        require(
            original == rebuilt,
            "Projection replay produced a different balance."
        );

        // Idempotency.
        int previousCount = application.events()
            .read("ACC-4001").size();

        Command duplicate = Command.deposit(
            "ACC-4001",
            100,
            4
        );

        commands.handle(duplicate);
        commands.handle(duplicate);

        int currentCount = application.events()
            .read("ACC-4001").size();

        require(
            currentCount == previousCount + 1,
            "Duplicate command created additional events."
        );

        System.out.println("\nProjection rebuild verified.");
        System.out.println("Idempotency verified.");
        System.out.println("All CQRS tests passed.");
    }
}
