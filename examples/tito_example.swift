// Together In Together Out - Swift example.
//
// Run: swift examples/tito_example.swift

/// A group released as a whole.
struct Released {
    let groupId: String
    let members: [String]
}

/// Minimal strict-order (head-of-line FIFO) TITO queue.
struct TitoQueue {
    private struct Group {
        let id: String
        let members: [String]
        var ready: Set<String> = []
    }

    private var order: [Group] = []
    private var groupOf: [String: Int] = [:]

    mutating func admit(_ groupId: String, _ members: [String]) {
        precondition(!members.isEmpty, "a group must contain at least one member")
        precondition(!order.contains { $0.id == groupId }, "duplicate group id: \(groupId)")
        var seen = Set<String>()
        for member in members {
            precondition(groupOf[member] == nil, "duplicate member: \(member)")
            precondition(seen.insert(member).inserted, "duplicate member: \(member)")
        }
        for member in members {
            groupOf[member] = order.count
        }
        order.append(Group(id: groupId, members: members))
    }

    mutating func markReady(_ member: String) {
        guard let index = groupOf[member] else {
            preconditionFailure("unknown member: \(member)")
        }
        order[index].ready.insert(member)
    }

    /// Releases the head group, or nil while it is not fully ready.
    mutating func release() -> Released? {
        guard let head = order.first, head.ready.count == head.members.count else {
            return nil
        }
        order.removeFirst()
        for member in head.members {
            groupOf.removeValue(forKey: member)
        }
        // Remaining groups shifted down by one, so refresh their indexes.
        for (index, group) in order.enumerated() {
            for member in group.members {
                groupOf[member] = index
            }
        }
        return Released(groupId: head.id, members: head.members)
    }
}

var queue = TitoQueue()

queue.admit("party-1", ["ann", "bob"])
print("admit party-1: ann, bob")
queue.admit("party-2", ["cy"])
print("admit party-2: cy")

for member in ["ann", "bob", "cy"] {
    queue.markReady(member)
    print("ready \(member)")
    if let released = queue.release() {
        print("release -> \(released.groupId) [\(released.members.joined(separator: " "))]")
    } else {
        print("release -> waiting")
    }
}
