import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/*
 * Enterprise-oriented consistent-hashing model for a distributed session
 * service.
 *
 * The domain model separates:
 * - physical members
 * - virtual ring positions
 * - membership state
 * - routing
 * - validation and operational policy
 *
 * Java 17 records provide immutable value objects for ring entries and
 * routing results. The service layer prevents invalid membership states
 * before the ring is rebuilt.
 */
public class ConsistentHashingEnterpriseDemo {

    private static final long MASK_64 = -1L;

    enum MemberState {
        ACTIVE,
        DRAINING,
        REMOVED
    }

    enum RoutingDecision {
        ROUTED,
        NO_ACTIVE_MEMBER,
        INVALID_KEY
    }

    record Member(
        String id,
        int virtualNodeCount,
        MemberState state
    ) {
        Member {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(state, "state");

            if (id.isBlank()) {
                throw new IllegalArgumentException("member id cannot be blank");
            }

            if (virtualNodeCount < 1) {
                throw new IllegalArgumentException(
                    "virtualNodeCount must be positive"
                );
            }
        }
    }

    record RingEntry(
        long position,
        String memberId,
        int replica
    ) {}

    record RouteResult(
        RoutingDecision decision,
        String key,
        String memberId,
        String reason
    ) {}

    static final class Ring {
        private final List<RingEntry> entries = new ArrayList<>();

        void rebuild(List<Member> members) {
            entries.clear();

            for (Member member : members) {
                if (member.state() != MemberState.ACTIVE) {
                    continue;
                }

                for (int replica = 0;
                     replica < member.virtualNodeCount();
                     replica++) {

                    long position = hash(
                        member.id() + "#vn:" + replica
                    );

                    entries.add(
                        new RingEntry(
                            position,
                            member.id(),
                            replica
                        )
                    );
                }
            }

            entries.sort(
                Comparator
                    .comparingLong(RingEntry::position)
                    .thenComparing(RingEntry::memberId)
                    .thenComparingInt(RingEntry::replica)
            );
        }

        String owner(long keyHash) {
            if (entries.isEmpty()) {
                throw new IllegalStateException(
                    "no active members are available"
                );
            }

            int low = 0;
            int high = entries.size();

            /*
             * Binary search locates the first clockwise ring position.
             * The wrap-around case maps a hash larger than every ring
             * position to the first entry.
             */
            while (low < high) {
                int middle = low + (high - low) / 2;

                if (compareUnsigned(
                    entries.get(middle).position(),
                    keyHash
                ) >= 0) {
                    high = middle;
                } else {
                    low = middle + 1;
                }
            }

            int index = low == entries.size() ? 0 : low;
            return entries.get(index).memberId();
        }

        int size() {
            return entries.size();
        }

        List<RingEntry> sample(int count) {
            return List.copyOf(
                entries.subList(
                    0,
                    Math.min(count, entries.size())
                )
            );
        }
    }

    static final class RoutingService {
        private final Map<String, Member> members = new TreeMap<>();
        private final Ring ring = new Ring();

        void register(Member member) {
            if (members.containsKey(member.id())) {
                throw new IllegalStateException(
                    "member already exists: " + member.id()
                );
            }

            members.put(member.id(), member);
            rebuild();
        }

        void changeState(String memberId, MemberState state) {
            Member current = requireMember(memberId);

            if (current.state() == MemberState.REMOVED) {
                throw new IllegalStateException(
                    "removed member cannot change state"
                );
            }

            if (state == MemberState.REMOVED) {
                members.put(
                    memberId,
                    new Member(
                        current.id(),
                        current.virtualNodeCount(),
                        MemberState.REMOVED
                    )
                );
            } else {
                members.put(
                    memberId,
                    new Member(
                        current.id(),
                        current.virtualNodeCount(),
                        state
                    )
                );
            }

            rebuild();
        }

        RouteResult route(String key) {
            if (key == null || key.isBlank()) {
                return new RouteResult(
                    RoutingDecision.INVALID_KEY,
                    key,
                    null,
                    "routing key must be non-empty"
                );
            }

            if (activeMembers().isEmpty()) {
                return new RouteResult(
                    RoutingDecision.NO_ACTIVE_MEMBER,
                    key,
                    null,
                    "there are no active ring members"
                );
            }

            String memberId = ring.owner(hash(key));

            return new RouteResult(
                RoutingDecision.ROUTED,
                key,
                memberId,
                "clockwise virtual-node ownership"
            );
        }

        Map<String, Integer> distribution(
            List<String> keys
        ) {
            Map<String, Integer> result = new TreeMap<>();

            for (Member member : activeMembers()) {
                result.put(member.id(), 0);
            }

            for (String key : keys) {
                RouteResult route = route(key);

                if (route.decision() == RoutingDecision.ROUTED) {
                    result.compute(
                        route.memberId(),
                        (ignored, count) -> count + 1
                    );
                }
            }

            return result;
        }

        List<Member> activeMembers() {
            return members.values()
                .stream()
                .filter(member -> member.state() == MemberState.ACTIVE)
                .toList();
        }

        List<RingEntry> ringSample(int count) {
            return ring.sample(count);
        }

        int ringSize() {
            return ring.size();
        }

        private Member requireMember(String memberId) {
            Member member = members.get(memberId);

            if (member == null) {
                throw new IllegalArgumentException(
                    "unknown member: " + memberId
                );
            }

            return member;
        }

        private void rebuild() {
            ring.rebuild(new ArrayList<>(members.values()));
        }
    }

    static long hash(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(
                value.getBytes(StandardCharsets.UTF_8)
            );

            long result = 0L;

            for (int index = 0; index < 8; index++) {
                result = (result << 8)
                    | (bytes[index] & 0xffL);
            }

            return result;
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(
                "SHA-256 is unavailable",
                error
            );
        }
    }

    static int compareUnsigned(long left, long right) {
        return Long.compareUnsigned(left, right);
    }

    static List<String> generateKeys(int count) {
        List<String> keys = new ArrayList<>(count);

        for (int index = 0; index < count; index++) {
            keys.add(
                "customer:" + (index % 1000)
                    + ":session:" + index
            );
        }

        return keys;
    }

    static int countMoved(
        Map<String, String> before,
        Map<String, String> after
    ) {
        int moved = 0;

        for (String key : before.keySet()) {
            if (!Objects.equals(
                before.get(key),
                after.get(key)
            )) {
                moved++;
            }
        }

        return moved;
    }

    static Map<String, String> ownershipSnapshot(
        RoutingService service,
        List<String> keys
    ) {
        Map<String, String> result = new HashMap<>();

        for (String key : keys) {
            RouteResult route = service.route(key);

            if (route.decision() == RoutingDecision.ROUTED) {
                result.put(key, route.memberId());
            }
        }

        return result;
    }

    public static void main(String[] args) {
        RoutingService service = new RoutingService();

        service.register(
            new Member("session-a", 128, MemberState.ACTIVE)
        );
        service.register(
            new Member("session-b", 128, MemberState.ACTIVE)
        );
        service.register(
            new Member("session-c", 256, MemberState.ACTIVE)
        );

        List<String> keys = generateKeys(50_000);

        System.out.println("=== Enterprise session routing ===");
        System.out.println(
            "Active members: "
                + service.activeMembers().stream()
                    .map(Member::id)
                    .toList()
        );
        System.out.println(
            "Virtual ring positions: "
                + service.ringSize()
        );

        System.out.println("\nDistribution:");
        service.distribution(keys)
            .forEach(
                (member, count) ->
                    System.out.printf(
                        "%-14s %7d%n",
                        member,
                        count
                    )
            );

        System.out.println("\nSelected routes:");

        for (String key : List.of(
            "customer:17:session:44",
            "customer:19:session:81",
            "customer:900:session:1001"
        )) {
            System.out.println(service.route(key));
        }

        System.out.println("\nRing sample:");

        for (RingEntry entry : service.ringSample(6)) {
            System.out.println(entry);
        }

        Map<String, String> before =
            ownershipSnapshot(service, keys);

        System.out.println("\nAdding session-d:");

        service.register(
            new Member("session-d", 128, MemberState.ACTIVE)
        );

        Map<String, String> after =
            ownershipSnapshot(service, keys);

        int moved = countMoved(before, after);

        System.out.printf(
            "Moved sessions: %d/%d (%.2f%%)%n",
            moved,
            keys.size(),
            moved * 100.0 / keys.size()
        );

        System.out.println("\nTransitioning session-b to DRAINING:");

        service.changeState(
            "session-b",
            MemberState.DRAINING
        );

        System.out.println(
            "Active members after drain: "
                + service.activeMembers().stream()
                    .map(Member::id)
                    .toList()
        );

        System.out.println(
            "Distribution after drain:"
        );

        service.distribution(keys)
            .forEach(
                (member, count) ->
                    System.out.printf(
                        "%-14s %7d%n",
                        member,
                        count
                    )
            );

        System.out.println("\nValidation:");

        System.out.println(
            service.route("").reason()
        );

        try {
            service.changeState(
                "unknown",
                MemberState.ACTIVE
            );
        } catch (IllegalArgumentException error) {
            System.out.println(
                "Unknown member rejected: "
                    + error.getMessage()
            );
        }

        /*
         * A ring is a routing abstraction, not a replication mechanism.
         * A production session service can use the selected member as the
         * primary owner and independently place replicas on subsequent
         * clockwise distinct members. Membership transitions should also be
         * coordinated so a draining member can transfer state before it is
         * physically removed.
         */
        System.out.println("\nDesign properties:");
        System.out.println(
            "Virtual nodes represent heterogeneous capacity."
        );
        System.out.println(
            "Unsigned 64-bit comparison preserves ring ordering."
        );
        System.out.println(
            "Binary search provides logarithmic lookup."
        );
        System.out.println(
            "Membership state prevents draining members from new ownership."
        );
    }
}
