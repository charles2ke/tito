// Together In Together Out - Java example.
//
// Run: javac -d /tmp/tito examples/TitoExample.java
//      && java -cp /tmp/tito TitoExample

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class TitoExample {

    /** Raised when an operation would violate the TITO invariants. */
    static final class TitoException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        TitoException(String message) {
            super(message);
        }
    }

    /**
     * A set of members that entered the queue together. A group is only ever
     * released as a whole: it departs once every member has been marked ready.
     */
    static final class Group {
        private final String groupId;
        private final List<String> members;
        private final LinkedHashMap<String, Boolean> ready;
        private int readyCount;

        Group(String groupId, List<String> members) {
            List<String> memberList = new ArrayList<>(members);
            if (memberList.isEmpty()) {
                throw new TitoException("group " + groupId + " must contain at least one member");
            }
            LinkedHashMap<String, Boolean> readyMap = new LinkedHashMap<>();
            for (String member : memberList) {
                readyMap.put(member, false);
            }
            if (readyMap.size() != memberList.size()) {
                throw new TitoException("group " + groupId + " contains duplicate members");
            }
            this.groupId = groupId;
            this.members = memberList;
            this.ready = readyMap;
        }

        String groupId() {
            return groupId;
        }

        /** The members of this group, in the order they were admitted. */
        List<String> members() {
            return members;
        }

        /** Members already marked ready, in admission order. */
        List<String> readyMembers() {
            List<String> result = new ArrayList<>();
            for (String member : members) {
                if (ready.get(member)) {
                    result.add(member);
                }
            }
            return result;
        }

        /** Members not yet marked ready, in admission order. */
        List<String> waitingMembers() {
            List<String> result = new ArrayList<>();
            for (String member : members) {
                if (!ready.get(member)) {
                    result.add(member);
                }
            }
            return result;
        }

        /** How many members have been marked ready. */
        int readyCount() {
            return readyCount;
        }

        /** True once every member of the group is ready to depart. */
        boolean isReady() {
            return readyCount == members.size();
        }

        /** Number of members admitted with the group. */
        int size() {
            return members.size();
        }

        /** Mark one member ready. Returns true if the whole group is ready. */
        boolean markReady(String member) {
            Boolean already = ready.get(member);
            if (already == null) {
                throw new TitoException(member + " is not a member of group " + groupId);
            }
            if (!already) {
                ready.put(member, true);
                readyCount++;
            }
            return isReady();
        }

        boolean contains(String member) {
            return ready.containsKey(member);
        }

        @Override
        public String toString() {
            return groupId + " [" + String.join(" ", members) + "]";
        }
    }

    /**
     * A queue that admits and releases members group by group. Strict order
     * (the default) is head-of-line FIFO: only the oldest waiting group may
     * depart. Relaxed order lets any fully ready group depart, oldest first, so
     * a waiting group does not block the ready groups behind it.
     */
    static final class TitoQueue {
        private final boolean strictOrder;
        private final LinkedHashMap<String, Group> groups = new LinkedHashMap<>();
        private final Map<String, String> memberIndex = new HashMap<>();

        TitoQueue() {
            this(true);
        }

        TitoQueue(boolean strictOrder) {
            this.strictOrder = strictOrder;
        }

        /** The ordering policy: head-of-line FIFO when true. */
        boolean strictOrder() {
            return strictOrder;
        }

        /** Admit members as one group. Returns the admitted group. */
        Group admit(String groupId, List<String> members) {
            Group group = new Group(groupId, members);
            if (groups.containsKey(groupId)) {
                throw new TitoException("group " + groupId + " is already in the queue");
            }
            List<String> queued = new ArrayList<>();
            for (String member : group.members()) {
                if (memberIndex.containsKey(member)) {
                    queued.add(member);
                }
            }
            if (!queued.isEmpty()) {
                throw new TitoException("members already in the queue: " + String.join(" ", queued));
            }
            groups.put(groupId, group);
            for (String member : group.members()) {
                memberIndex.put(member, groupId);
            }
            return group;
        }

        /** Mark a queued member ready. Returns true if its group is ready. */
        boolean markReady(String member) {
            Group group = groupOf(member);
            if (group == null) {
                throw new TitoException(member + " is not in the queue");
            }
            return group.markReady(member);
        }

        /** Mark every member of a queued group ready. */
        boolean markGroupReady(String groupId) {
            Group group = groups.get(groupId);
            if (group == null) {
                throw new TitoException("group " + groupId + " is not in the queue");
            }
            for (String member : group.members()) {
                group.markReady(member);
            }
            return true;
        }

        /** The group a queued member belongs to, or null if not queued. */
        Group groupOf(String member) {
            String groupId = memberIndex.get(member);
            if (groupId == null) {
                return null;
            }
            return groups.get(groupId);
        }

        /** The next group that would be released, without releasing it. */
        Group peek() {
            for (Group group : groups.values()) {
                if (group.isReady()) {
                    return group;
                }
                if (strictOrder) {
                    // Head of the line blocks every group behind it.
                    return null;
                }
            }
            return null;
        }

        /** Release the next fully ready group, or null if none can depart. */
        Group release() {
            Group group = peek();
            if (group == null) {
                return null;
            }
            remove(group);
            return group;
        }

        /** Release every group that can currently depart, in order. */
        List<Group> releaseAll() {
            List<Group> released = new ArrayList<>();
            while (true) {
                Group group = release();
                if (group == null) {
                    return released;
                }
                released.add(group);
            }
        }

        /** Withdraw a waiting group, ready or not, and return it. */
        Group cancel(String groupId) {
            Group group = groups.get(groupId);
            if (group == null) {
                throw new TitoException("group " + groupId + " is not in the queue");
            }
            remove(group);
            return group;
        }

        /** Withdraw every waiting group, in arrival order, and return them. */
        List<Group> clear() {
            List<Group> cleared = new ArrayList<>(groups.values());
            groups.clear();
            memberIndex.clear();
            return cleared;
        }

        /** Waiting groups, in arrival order. */
        List<Group> groups() {
            return new ArrayList<>(groups.values());
        }

        /** Number of waiting groups. */
        int size() {
            return groups.size();
        }

        boolean contains(String member) {
            return memberIndex.containsKey(member);
        }

        private void remove(Group group) {
            groups.remove(group.groupId());
            for (String member : group.members()) {
                memberIndex.remove(member);
            }
        }
    }

    public static void main(String[] args) {
        strictOrderDemo();
        System.out.println();
        relaxedOrderDemo();
        System.out.println();
        cancelAndClearDemo();
        System.out.println();
        errorDemo();
    }

    // Head-of-line FIFO: party-2 waits behind party-1 until it departs.
    private static void strictOrderDemo() {
        System.out.println("-- strict order --");
        TitoQueue queue = new TitoQueue();
        System.out.println("admit " + queue.admit("party-1", List.of("ann", "bob")));
        System.out.println("admit " + queue.admit("party-2", List.of("cy")));
        System.out.println("len " + queue.size() + ", groups " + showIds(queue.groups()));
        System.out.println("contains ann " + flag(queue.contains("ann")) + ", contains zoe " + flag(queue.contains("zoe")));

        Group party1 = queue.groupOf("bob");
        System.out.println("group_of bob -> " + party1.groupId());
        System.out.println("party-1: size " + party1.size() + ", contains ann " + flag(party1.contains("ann"))
                + ", contains zoe " + flag(party1.contains("zoe")));

        System.out.println("mark_ready ann -> group ready " + flag(queue.markReady("ann")));
        System.out.println("party-1: " + party1.readyCount() + "/" + party1.size() + " ready ["
                + String.join(" ", party1.readyMembers()) + "] waiting [" + String.join(" ", party1.waitingMembers())
                + "] is_ready " + flag(party1.isReady()));
        System.out.println("peek -> " + show(queue.peek()));
        System.out.println("release -> " + show(queue.release()));

        System.out.println("party-1.mark_ready bob -> group ready " + flag(party1.markReady("bob")));
        System.out.println("party-1: " + party1.readyCount() + "/" + party1.size() + " ready ["
                + String.join(" ", party1.readyMembers()) + "] waiting [" + String.join(" ", party1.waitingMembers())
                + "] is_ready " + flag(party1.isReady()));
        System.out.println("peek -> " + show(queue.peek()));
        System.out.println("release -> " + show(queue.release()));

        System.out.println("mark_group_ready party-2 -> " + flag(queue.markGroupReady("party-2")));
        System.out.println("release_all -> " + showAll(queue.releaseAll()));
        System.out.println("len " + queue.size());
    }

    // Without strict order, ready party-4 leaves ahead of waiting party-3.
    private static void relaxedOrderDemo() {
        System.out.println("-- relaxed order --");
        TitoQueue queue = new TitoQueue(false);
        System.out.println("strict_order " + flag(queue.strictOrder()));
        System.out.println("admit " + queue.admit("party-3", List.of("dee", "eli")));
        System.out.println("admit " + queue.admit("party-4", List.of("fay")));

        System.out.println("mark_group_ready party-4 -> " + flag(queue.markGroupReady("party-4")));
        System.out.println("peek -> " + show(queue.peek()));
        System.out.println("release -> " + show(queue.release()));

        System.out.println("mark_ready dee -> group ready " + flag(queue.markReady("dee")));
        System.out.println("release -> " + show(queue.release()));
        System.out.println("mark_ready eli -> group ready " + flag(queue.markReady("eli")));
        System.out.println("release_all -> " + showAll(queue.releaseAll()));
        System.out.println("len " + queue.size());
    }

    // Cancelling is the only way a group leaves before it is fully ready.
    private static void cancelAndClearDemo() {
        System.out.println("-- cancel and clear --");
        TitoQueue queue = new TitoQueue();
        System.out.println("admit " + queue.admit("party-5", List.of("gil", "hal")));
        System.out.println("admit " + queue.admit("party-6", List.of("ivy")));
        System.out.println("admit " + queue.admit("party-7", List.of("jay")));

        System.out.println("mark_ready gil -> group ready " + flag(queue.markReady("gil")));
        Group cancelled = queue.cancel("party-5");
        System.out.println("cancel party-5 -> " + cancelled + " " + cancelled.readyCount() + "/" + cancelled.size() + " ready");
        System.out.println("groups " + showIds(queue.groups()));
        System.out.println("clear -> " + showAll(queue.clear()));
        System.out.println("len " + queue.size() + ", contains ivy " + flag(queue.contains("ivy")));
    }

    // Every operation that would break the TITO invariants is rejected.
    private static void errorDemo() {
        System.out.println("-- errors --");
        TitoQueue queue = new TitoQueue();
        System.out.println("admit " + queue.admit("party-8", List.of("kim")));

        attempt("admit party-8 [kim]", () -> queue.admit("party-8", List.of("kim")));
        attempt("admit party-9 []", () -> queue.admit("party-9", List.of()));
        attempt("admit party-9 [jay jay]", () -> queue.admit("party-9", List.of("jay", "jay")));
        attempt("admit party-9 [kim]", () -> queue.admit("party-9", List.of("kim")));
        attempt("mark_ready zoe", () -> queue.markReady("zoe"));
        attempt("party-8.mark_ready zoe", () -> queue.groupOf("kim").markReady("zoe"));
        attempt("mark_group_ready party-9", () -> queue.markGroupReady("party-9"));
        attempt("cancel party-9", () -> queue.cancel("party-9"));
    }

    // Format a boolean the same way in every example language.
    private static String flag(boolean value) {
        return value ? "true" : "false";
    }

    // Format an optional group, as returned by peek() and release().
    private static String show(Group group) {
        return group == null ? "waiting" : group.toString();
    }

    // Format the group lists returned by releaseAll() and clear().
    private static String showAll(List<Group> groups) {
        if (groups.isEmpty()) {
            return "none";
        }
        List<String> parts = new ArrayList<>();
        for (Group group : groups) {
            parts.add(group.toString());
        }
        return String.join(", ", parts);
    }

    // Format the group ids of the waiting groups.
    private static String showIds(List<Group> groups) {
        if (groups.isEmpty()) {
            return "none";
        }
        List<String> parts = new ArrayList<>();
        for (Group group : groups) {
            parts.add(group.groupId());
        }
        return String.join(" ", parts);
    }

    // Run an operation that must fail, and print the reported reason.
    private static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> no error");
        } catch (TitoException error) {
            System.out.println(label + " -> " + error.getMessage());
        }
    }
}
