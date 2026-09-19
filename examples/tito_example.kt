// Together In Together Out - Kotlin example.
//
// Run: kotlinc examples/tito_example.kt -include-runtime -d /tmp/tito.jar
//      && java -jar /tmp/tito.jar

/** A group released as a whole. */
data class Released(val groupId: String, val members: List<String>)

/** Minimal strict-order (head-of-line FIFO) TITO queue. */
class TitoQueue {
    private val order = ArrayDeque<String>()
    private val groups = HashMap<String, LinkedHashMap<String, Boolean>>()
    private val groupOf = HashMap<String, String>()

    fun admit(groupId: String, members: List<String>) {
        require(members.isNotEmpty()) { "a group must contain at least one member" }
        require(!groups.containsKey(groupId)) { "duplicate group id: $groupId" }
        val ready = LinkedHashMap<String, Boolean>()
        for (member in members) {
            require(!groupOf.containsKey(member) && !ready.containsKey(member)) {
                "duplicate member: $member"
            }
            ready[member] = false
        }
        for (member in members) {
            groupOf[member] = groupId
        }
        groups[groupId] = ready
        order.addLast(groupId)
    }

    fun markReady(member: String) {
        val groupId = requireNotNull(groupOf[member]) { "unknown member: $member" }
        groups.getValue(groupId)[member] = true
    }

    /** Releases the head group, or null while it is not fully ready. */
    fun release(): Released? {
        val groupId = order.firstOrNull() ?: return null
        val ready = groups.getValue(groupId)
        if (ready.values.any { !it }) {
            return null
        }
        order.removeFirst()
        groups.remove(groupId)
        val members = ready.keys.toList()
        for (member in members) {
            groupOf.remove(member)
        }
        return Released(groupId, members)
    }
}

fun main() {
    val queue = TitoQueue()

    queue.admit("party-1", listOf("ann", "bob"))
    println("admit party-1: ann, bob")
    queue.admit("party-2", listOf("cy"))
    println("admit party-2: cy")

    for (member in listOf("ann", "bob", "cy")) {
        queue.markReady(member)
        println("ready $member")
        val released = queue.release()
        if (released == null) {
            println("release -> waiting")
        } else {
            println("release -> ${released.groupId} [${released.members.joinToString(" ")}]")
        }
    }
}
