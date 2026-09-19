// Together In Together Out - Java example.
//
// Run: javac -d /tmp/tito examples/TitoExample.java
//      && java -cp /tmp/tito TitoExample

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class TitoExample {

    /** A group released as a whole. */
    static final class Released {
        final String groupId;
        final List<String> members;

        Released(String groupId, List<String> members) {
            this.groupId = groupId;
            this.members = members;
        }
    }

    /** Minimal strict-order (head-of-line FIFO) TITO queue. */
    static final class TitoQueue {
        private final Deque<String> order = new ArrayDeque<>();
        private final Map<String, LinkedHashMap<String, Boolean>> groups = new HashMap<>();
        private final Map<String, String> groupOf = new HashMap<>();

        void admit(String groupId, List<String> members) {
            if (members.isEmpty()) {
                throw new IllegalArgumentException("a group must contain at least one member");
            }
            if (groups.containsKey(groupId)) {
                throw new IllegalArgumentException("duplicate group id: " + groupId);
            }
            LinkedHashMap<String, Boolean> ready = new LinkedHashMap<>();
            for (String member : members) {
                if (groupOf.containsKey(member) || ready.containsKey(member)) {
                    throw new IllegalArgumentException("duplicate member: " + member);
                }
                ready.put(member, false);
            }
            for (String member : members) {
                groupOf.put(member, groupId);
            }
            groups.put(groupId, ready);
            order.addLast(groupId);
        }

        void markReady(String member) {
            String groupId = groupOf.get(member);
            if (groupId == null) {
                throw new IllegalArgumentException("unknown member: " + member);
            }
            groups.get(groupId).put(member, true);
        }

        /** Release the head group, or null while it is not fully ready. */
        Released release() {
            String groupId = order.peekFirst();
            if (groupId == null) {
                return null;
            }
            Map<String, Boolean> ready = groups.get(groupId);
            for (boolean isReady : ready.values()) {
                if (!isReady) {
                    return null;
                }
            }
            order.removeFirst();
            groups.remove(groupId);
            List<String> members = new ArrayList<>(ready.keySet());
            for (String member : members) {
                groupOf.remove(member);
            }
            return new Released(groupId, members);
        }
    }

    public static void main(String[] args) {
        TitoQueue queue = new TitoQueue();

        queue.admit("party-1", List.of("ann", "bob"));
        System.out.println("admit party-1: ann, bob");
        queue.admit("party-2", List.of("cy"));
        System.out.println("admit party-2: cy");

        for (String member : List.of("ann", "bob", "cy")) {
            queue.markReady(member);
            System.out.println("ready " + member);
            Released released = queue.release();
            if (released == null) {
                System.out.println("release -> waiting");
            } else {
                System.out.println(
                        "release -> " + released.groupId + " [" + String.join(" ", released.members) + "]");
            }
        }
    }
}
