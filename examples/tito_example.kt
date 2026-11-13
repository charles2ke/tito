// Together In Together Out - Kotlin example.
//
// Run: kotlinc examples/tito_example.kt -include-runtime -d /tmp/tito.jar
//      && java -jar /tmp/tito.jar

/** Raised when an operation would violate the TITO invariants. */
class TitoException(message: String) : RuntimeException(message)

/**
 * A set of members that entered the queue together. A group is only ever
 * released as a whole: it departs once every member is marked ready.
 */
class Group(val groupId: String, initialMembers: List<String>) {
    /** The members of this group, in the order they were admitted. */
    val members: List<String> = initialMembers.toList()

    private val ready = LinkedHashMap<String, Boolean>()

    /** How many members have been marked ready. */
    var readyCount: Int = 0
        private set

    init {
        if (members.isEmpty()) {
            throw TitoException("group $groupId must contain at least one member")
        }
        for (member in members) {
            ready[member] = false
        }
        if (ready.size != members.size) {
            throw TitoException("group $groupId contains duplicate members")
        }
    }

    /** Members already marked ready, in admission order. */
    val readyMembers: List<String>
        get() = members.filter { ready.getValue(it) }

    /** Members not yet marked ready, in admission order. */
    val waitingMembers: List<String>
        get() = members.filter { !ready.getValue(it) }

    /** True once every member of the group is ready to depart. */
    val isReady: Boolean
        get() = readyCount == members.size

    /** Number of members admitted with the group. */
    val size: Int
        get() = members.size

    /** Mark one member ready. Returns true if the whole group is ready. */
    fun markReady(member: String): Boolean {
        val already = ready[member] ?: throw TitoException("$member is not a member of group $groupId")
        if (!already) {
            ready[member] = true
            readyCount++
        }
        return isReady
    }

    /** Take back a member's readiness, so the group waits for it again. */
    fun markWaiting(member: String) {
        val wasReady = ready[member] ?: throw TitoException("$member is not a member of group $groupId")
        if (wasReady) {
            ready[member] = false
            readyCount--
        }
    }

    operator fun contains(member: String): Boolean = ready.containsKey(member)

    override fun toString(): String = "$groupId [${members.joinToString(" ")}]"
}

/**
 * A queue that admits and releases members group by group. Strict order (the
 * default) is head-of-line FIFO: only the oldest waiting group may depart.
 * Relaxed order lets any fully ready group depart, oldest first, so a waiting
 * group does not block the ready groups behind it.
 */
class TitoQueue(val strictOrder: Boolean = true) {
    private val groupsById = LinkedHashMap<String, Group>()
    private val memberIndex = HashMap<String, String>()

    /** Admit members as one group. Returns the admitted group. */
    fun admit(groupId: String, members: List<String>): Group {
        val group = Group(groupId, members)
        if (groupsById.containsKey(groupId)) {
            throw TitoException("group $groupId is already in the queue")
        }
        val queued = group.members.filter { memberIndex.containsKey(it) }
        if (queued.isNotEmpty()) {
            throw TitoException("members already in the queue: ${queued.joinToString(" ")}")
        }
        groupsById[groupId] = group
        for (member in group.members) {
            memberIndex[member] = groupId
        }
        return group
    }

    /** Mark a queued member ready. Returns true if its group is ready. */
    fun markReady(member: String): Boolean {
        val group = groupOf(member) ?: throw TitoException("$member is not in the queue")
        return group.markReady(member)
    }

    /** Take back a queued member's readiness; its group waits for it again. */
    fun markWaiting(member: String) {
        val group = groupOf(member) ?: throw TitoException("$member is not in the queue")
        group.markWaiting(member)
    }

    /** Mark every member of a queued group ready. */
    fun markGroupReady(groupId: String): Boolean {
        val group = groupsById[groupId] ?: throw TitoException("group $groupId is not in the queue")
        for (member in group.members) {
            group.markReady(member)
        }
        return true
    }

    /** The waiting group with this id, or null if it is not in the queue. */
    fun get(groupId: String): Group? = groupsById[groupId]

    /** The group a queued member belongs to, or null if not queued. */
    fun groupOf(member: String): Group? {
        val groupId = memberIndex[member] ?: return null
        return groupsById[groupId]
    }

    /** The next group that would be released, without releasing it. */
    fun peek(): Group? {
        for (group in groupsById.values) {
            if (group.isReady) {
                return group
            }
            if (strictOrder) {
                // Head of the line blocks every group behind it.
                return null
            }
        }
        return null
    }

    /** Release the next fully ready group, or null if none can depart. */
    fun release(): Group? {
        val group = peek() ?: return null
        remove(group)
        return group
    }

    /** Release every group that can currently depart, in order. */
    fun releaseAll(): List<Group> {
        val released = mutableListOf<Group>()
        while (true) {
            val group = release() ?: return released
            released.add(group)
        }
    }

    /** Withdraw a waiting group, ready or not, and return it. */
    fun cancel(groupId: String): Group {
        val group = groupsById[groupId] ?: throw TitoException("group $groupId is not in the queue")
        remove(group)
        return group
    }

    /** Withdraw every waiting group, in arrival order, and return them. */
    fun clear(): List<Group> {
        val cleared = groupsById.values.toList()
        groupsById.clear()
        memberIndex.clear()
        return cleared
    }

    /** Waiting groups, in arrival order. */
    val groups: List<Group>
        get() = groupsById.values.toList()

    /** Number of waiting groups. */
    val size: Int
        get() = groupsById.size

    operator fun contains(member: String): Boolean = memberIndex.containsKey(member)

    private fun remove(group: Group) {
        groupsById.remove(group.groupId)
        for (member in group.members) {
            memberIndex.remove(member)
        }
    }
}

// Format a boolean the same way in every example language.
private fun flag(value: Boolean): String = if (value) "true" else "false"

// Format an optional group, as returned by peek() and release().
private fun show(group: Group?): String = group?.toString() ?: "waiting"

// Format the optional group returned by get().
private fun showFound(group: Group?): String = group?.toString() ?: "none"

// Format a group's readiness the same way in every status line.
private fun showStatus(group: Group): String =
    "${group.groupId}: ${group.readyCount}/${group.size} ready [${group.readyMembers.joinToString(" ")}] " +
        "waiting [${group.waitingMembers.joinToString(" ")}] is_ready ${flag(group.isReady)}"

// Format the group lists returned by releaseAll() and clear().
private fun showAll(groups: List<Group>): String =
    if (groups.isEmpty()) "none" else groups.joinToString(", ")

// Format the group ids of the waiting groups.
private fun showIds(groups: List<Group>): String =
    if (groups.isEmpty()) "none" else groups.joinToString(" ") { it.groupId }

// Run an operation that must fail, and print the reported reason.
private fun attempt(label: String, action: () -> Unit) {
    try {
        action()
        println("$label -> no error")
    } catch (error: TitoException) {
        println("$label -> ${error.message}")
    }
}

// Head-of-line FIFO: party-2 waits behind party-1 until it departs.
private fun strictOrderDemo() {
    println("-- strict order --")
    val queue = TitoQueue()
    println("admit ${queue.admit("party-1", listOf("ann", "bob"))}")
    println("admit ${queue.admit("party-2", listOf("cy"))}")
    println("len ${queue.size}, groups ${showIds(queue.groups)}")
    println("contains ann ${flag("ann" in queue)}, contains zoe ${flag("zoe" in queue)}")
    println("get party-2 -> ${showFound(queue.get("party-2"))}")

    val party1 = queue.groupOf("bob")!!
    println("group_of bob -> ${party1.groupId}")
    println("party-1: size ${party1.size}, contains ann ${flag("ann" in party1)}, contains zoe ${flag("zoe" in party1)}")

    println("mark_ready ann -> group ready ${flag(queue.markReady("ann"))}")
    println(showStatus(party1))
    println("peek -> ${show(queue.peek())}")
    println("release -> ${show(queue.release())}")

    println("party-1.mark_ready bob -> group ready ${flag(party1.markReady("bob"))}")
    println(showStatus(party1))
    println("peek -> ${show(queue.peek())}")
    println("release -> ${show(queue.release())}")

    println("mark_group_ready party-2 -> ${flag(queue.markGroupReady("party-2"))}")
    println("release_all -> ${showAll(queue.releaseAll())}")
    println("get party-2 -> ${showFound(queue.get("party-2"))}")
    println("len ${queue.size}")
}

// Without strict order, ready party-4 leaves ahead of waiting party-3.
// Taking back a member's readiness makes party-3 wait for it again.
private fun relaxedOrderDemo() {
    println("-- relaxed order --")
    val queue = TitoQueue(strictOrder = false)
    println("strict_order ${flag(queue.strictOrder)}")
    val party3 = queue.admit("party-3", listOf("dee", "eli"))
    println("admit $party3")
    println("admit ${queue.admit("party-4", listOf("fay"))}")

    println("mark_group_ready party-4 -> ${flag(queue.markGroupReady("party-4"))}")
    println("peek -> ${show(queue.peek())}")
    println("release -> ${show(queue.release())}")

    println("mark_ready dee -> group ready ${flag(queue.markReady("dee"))}")
    println("release -> ${show(queue.release())}")
    println("mark_ready eli -> group ready ${flag(queue.markReady("eli"))}")
    queue.markWaiting("dee")
    println("mark_waiting dee")
    println(showStatus(party3))
    println("release -> ${show(queue.release())}")
    party3.markWaiting("eli")
    println("party-3.mark_waiting eli")
    println(showStatus(party3))
    println("mark_group_ready party-3 -> ${flag(queue.markGroupReady("party-3"))}")
    println("release_all -> ${showAll(queue.releaseAll())}")
    println("len ${queue.size}")
}

// Cancelling is the only way a group leaves before it is fully ready.
private fun cancelAndClearDemo() {
    println("-- cancel and clear --")
    val queue = TitoQueue()
    println("admit ${queue.admit("party-5", listOf("gil", "hal"))}")
    println("admit ${queue.admit("party-6", listOf("ivy"))}")
    println("admit ${queue.admit("party-7", listOf("jay"))}")

    println("mark_ready gil -> group ready ${flag(queue.markReady("gil"))}")
    val cancelled = queue.cancel("party-5")
    println("cancel party-5 -> $cancelled ${cancelled.readyCount}/${cancelled.size} ready")
    println("groups ${showIds(queue.groups)}")
    println("clear -> ${showAll(queue.clear())}")
    println("len ${queue.size}, contains ivy ${flag("ivy" in queue)}")
}

// Every operation that would break the TITO invariants is rejected.
private fun errorDemo() {
    println("-- errors --")
    val queue = TitoQueue()
    println("admit ${queue.admit("party-8", listOf("kim"))}")

    attempt("admit party-8 [kim]") { queue.admit("party-8", listOf("kim")) }
    attempt("admit party-9 []") { queue.admit("party-9", listOf()) }
    attempt("admit party-9 [jay jay]") { queue.admit("party-9", listOf("jay", "jay")) }
    attempt("admit party-9 [kim]") { queue.admit("party-9", listOf("kim")) }
    attempt("mark_ready zoe") { queue.markReady("zoe") }
    attempt("mark_waiting zoe") { queue.markWaiting("zoe") }
    attempt("party-8.mark_ready zoe") { queue.groupOf("kim")!!.markReady("zoe") }
    attempt("party-8.mark_waiting zoe") { queue.groupOf("kim")!!.markWaiting("zoe") }
    attempt("mark_group_ready party-9") { queue.markGroupReady("party-9") }
    attempt("cancel party-9") { queue.cancel("party-9") }
}

fun main() {
    strictOrderDemo()
    println()
    relaxedOrderDemo()
    println()
    cancelAndClearDemo()
    println()
    errorDemo()
}
