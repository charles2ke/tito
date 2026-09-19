// Together In Together Out - Swift example.
//
// Run: swift examples/tito_example.swift

/// Raised when an operation would violate the TITO invariants.
enum TitoError: Error, CustomStringConvertible {
    case emptyGroup(String)
    case duplicateMembers(String)
    case alreadyQueued(String)
    case membersQueued(String)
    case memberNotQueued(String)
    case notAMember(member: String, group: String)
    case groupNotQueued(String)

    var description: String {
        switch self {
        case .emptyGroup(let id):
            return "group \(id) must contain at least one member"
        case .duplicateMembers(let id):
            return "group \(id) contains duplicate members"
        case .alreadyQueued(let id):
            return "group \(id) is already in the queue"
        case .membersQueued(let members):
            return "members already in the queue: \(members)"
        case .memberNotQueued(let member):
            return "\(member) is not in the queue"
        case .notAMember(let member, let group):
            return "\(member) is not a member of group \(group)"
        case .groupNotQueued(let id):
            return "group \(id) is not in the queue"
        }
    }
}

/// A set of members admitted together. A reference type, so the group a caller
/// holds stays in step with the copy the queue tracks. It departs only once
/// every member has been marked ready.
final class Group: CustomStringConvertible {
    let groupID: String
    let members: [String]
    private var readyFlags: [String: Bool]
    private(set) var readyCount = 0

    init(_ groupID: String, _ members: [String]) throws {
        if members.isEmpty {
            throw TitoError.emptyGroup(groupID)
        }
        var flags: [String: Bool] = [:]
        for member in members {
            if flags[member] != nil {
                throw TitoError.duplicateMembers(groupID)
            }
            flags[member] = false
        }
        self.groupID = groupID
        self.members = members
        self.readyFlags = flags
    }

    /// Members already marked ready, in admission order.
    var readyMembers: [String] {
        return members.filter { readyFlags[$0] == true }
    }

    /// Members not yet marked ready, in admission order.
    var waitingMembers: [String] {
        return members.filter { readyFlags[$0] == false }
    }

    var isReady: Bool {
        return readyCount == members.count
    }

    /// Mark one member ready. Returns true once the whole group is ready.
    @discardableResult
    func markReady(_ member: String) throws -> Bool {
        guard let ready = readyFlags[member] else {
            throw TitoError.notAMember(member: member, group: groupID)
        }
        if !ready {
            readyFlags[member] = true
            readyCount += 1
        }
        return isReady
    }

    var count: Int {
        return members.count
    }

    func contains(_ member: String) -> Bool {
        return readyFlags[member] != nil
    }

    var description: String {
        return "\(groupID) [\(members.joined(separator: " "))]"
    }
}

/// A queue that admits and releases members group by group.
///
/// `strictOrder` true (the default policy) is head-of-line FIFO: only the
/// oldest waiting group may depart. `strictOrder` false lets any fully ready
/// group depart, still oldest first, so a waiting group does not block the
/// ready groups behind it.
final class TitoQueue {
    let strictOrder: Bool
    private var order: [Group] = []
    private var byID: [String: Group] = [:]
    private var memberIndex: [String: String] = [:]

    init(strictOrder: Bool = true) {
        self.strictOrder = strictOrder
    }

    /// Admit members as one group and return it.
    @discardableResult
    func admit(_ groupID: String, _ members: [String]) throws -> Group {
        let group = try Group(groupID, members)
        if byID[groupID] != nil {
            throw TitoError.alreadyQueued(groupID)
        }
        let queued = group.members.filter { memberIndex[$0] != nil }
        if !queued.isEmpty {
            throw TitoError.membersQueued(queued.joined(separator: " "))
        }
        order.append(group)
        byID[groupID] = group
        for member in group.members {
            memberIndex[member] = groupID
        }
        return group
    }

    /// Mark a queued member ready. Returns true once its group is ready.
    @discardableResult
    func markReady(_ member: String) throws -> Bool {
        guard let group = groupOf(member) else {
            throw TitoError.memberNotQueued(member)
        }
        return try group.markReady(member)
    }

    /// Mark every member of a queued group ready.
    @discardableResult
    func markGroupReady(_ groupID: String) throws -> Bool {
        guard let group = byID[groupID] else {
            throw TitoError.groupNotQueued(groupID)
        }
        for member in group.members {
            try group.markReady(member)
        }
        return true
    }

    /// The group a queued member belongs to, or nil if not queued.
    func groupOf(_ member: String) -> Group? {
        guard let groupID = memberIndex[member] else {
            return nil
        }
        return byID[groupID]
    }

    /// The next group that would be released, without releasing it.
    func peek() -> Group? {
        for group in order {
            if group.isReady {
                return group
            }
            if strictOrder {
                // Head of the line blocks every group behind it.
                return nil
            }
        }
        return nil
    }

    /// Release the next group that can depart, or nil.
    @discardableResult
    func release() -> Group? {
        guard let group = peek() else {
            return nil
        }
        remove(group)
        return group
    }

    /// Release every group that can currently depart, in order.
    func releaseAll() -> [Group] {
        var released: [Group] = []
        while let group = release() {
            released.append(group)
        }
        return released
    }

    /// Withdraw a waiting group, ready or not, and return it.
    @discardableResult
    func cancel(_ groupID: String) throws -> Group {
        guard let group = byID[groupID] else {
            throw TitoError.groupNotQueued(groupID)
        }
        remove(group)
        return group
    }

    /// Withdraw every waiting group, in arrival order, and return them.
    func clear() -> [Group] {
        let cleared = order
        order.removeAll()
        byID.removeAll()
        memberIndex.removeAll()
        return cleared
    }

    /// Waiting groups, in arrival order.
    var groups: [Group] {
        return order
    }

    var count: Int {
        return order.count
    }

    func contains(_ member: String) -> Bool {
        return memberIndex[member] != nil
    }

    private func remove(_ group: Group) {
        if let index = order.firstIndex(where: { $0 === group }) {
            order.remove(at: index)
        }
        byID.removeValue(forKey: group.groupID)
        for member in group.members {
            memberIndex.removeValue(forKey: member)
        }
    }
}

func flag(_ value: Bool) -> String {
    return value ? "true" : "false"
}

/// Format an optional group, as returned by peek and release.
func show(_ group: Group?) -> String {
    guard let group = group else {
        return "waiting"
    }
    return group.description
}

/// Format the group lists returned by releaseAll and clear.
func showAll(_ groups: [Group]) -> String {
    if groups.isEmpty {
        return "none"
    }
    return groups.map { $0.description }.joined(separator: ", ")
}

/// Format the ids of the waiting groups.
func showIDs(_ groups: [Group]) -> String {
    if groups.isEmpty {
        return "none"
    }
    return groups.map { $0.groupID }.joined(separator: " ")
}

/// Format a group's readiness the same way in both status lines.
func status(_ group: Group) -> String {
    return "\(group.readyCount)/\(group.count) ready [\(group.readyMembers.joined(separator: " "))]"
        + " waiting [\(group.waitingMembers.joined(separator: " "))] is_ready \(flag(group.isReady))"
}

/// Head-of-line FIFO: party-2 waits behind party-1 until it departs.
func strictOrderDemo() throws {
    print("-- strict order --")
    let queue = TitoQueue()
    print("admit \(try queue.admit("party-1", ["ann", "bob"]))")
    print("admit \(try queue.admit("party-2", ["cy"]))")
    print("len \(queue.count), groups \(showIDs(queue.groups))")
    print("contains ann \(flag(queue.contains("ann"))), contains zoe \(flag(queue.contains("zoe")))")

    guard let party1 = queue.groupOf("bob") else { return }
    print("group_of bob -> \(party1.groupID)")
    print("party-1: size \(party1.count), contains ann \(flag(party1.contains("ann"))), contains zoe \(flag(party1.contains("zoe")))")

    print("mark_ready ann -> group ready \(flag(try queue.markReady("ann")))")
    print("party-1: \(status(party1))")
    print("peek -> \(show(queue.peek()))")
    print("release -> \(show(queue.release()))")

    print("party-1.mark_ready bob -> group ready \(flag(try party1.markReady("bob")))")
    print("party-1: \(status(party1))")
    print("peek -> \(show(queue.peek()))")
    print("release -> \(show(queue.release()))")

    print("mark_group_ready party-2 -> \(flag(try queue.markGroupReady("party-2")))")
    print("release_all -> \(showAll(queue.releaseAll()))")
    print("len \(queue.count)")
}

/// Without strict order, ready party-4 leaves ahead of waiting party-3.
func relaxedOrderDemo() throws {
    print("-- relaxed order --")
    let queue = TitoQueue(strictOrder: false)
    print("strict_order \(flag(queue.strictOrder))")
    print("admit \(try queue.admit("party-3", ["dee", "eli"]))")
    print("admit \(try queue.admit("party-4", ["fay"]))")

    print("mark_group_ready party-4 -> \(flag(try queue.markGroupReady("party-4")))")
    print("peek -> \(show(queue.peek()))")
    print("release -> \(show(queue.release()))")

    print("mark_ready dee -> group ready \(flag(try queue.markReady("dee")))")
    print("release -> \(show(queue.release()))")
    print("mark_ready eli -> group ready \(flag(try queue.markReady("eli")))")
    print("release_all -> \(showAll(queue.releaseAll()))")
    print("len \(queue.count)")
}

/// Cancelling is the only way a group leaves before it is fully ready.
func cancelAndClearDemo() throws {
    print("-- cancel and clear --")
    let queue = TitoQueue()
    print("admit \(try queue.admit("party-5", ["gil", "hal"]))")
    print("admit \(try queue.admit("party-6", ["ivy"]))")
    print("admit \(try queue.admit("party-7", ["jay"]))")

    print("mark_ready gil -> group ready \(flag(try queue.markReady("gil")))")
    let cancelled = try queue.cancel("party-5")
    print("cancel party-5 -> \(cancelled) \(cancelled.readyCount)/\(cancelled.count) ready")
    print("groups \(showIDs(queue.groups))")
    print("clear -> \(showAll(queue.clear()))")
    print("len \(queue.count), contains ivy \(flag(queue.contains("ivy")))")
}

/// Run an operation that must fail, and print the reported reason.
func attempt(_ label: String, _ action: () throws -> Void) {
    do {
        try action()
        print("\(label) -> no error")
    } catch let error as TitoError {
        print("\(label) -> \(error.description)")
    } catch {
        print("\(label) -> \(error)")
    }
}

/// Every operation that would break the TITO invariants is rejected.
func errorDemo() {
    print("-- errors --")
    let queue = TitoQueue()
    do {
        print("admit \(try queue.admit("party-8", ["kim"]))")
    } catch {
        print("admit -> \(error)")
    }

    attempt("admit party-8 [kim]") { _ = try queue.admit("party-8", ["kim"]) }
    attempt("admit party-9 []") { _ = try queue.admit("party-9", []) }
    attempt("admit party-9 [jay jay]") { _ = try queue.admit("party-9", ["jay", "jay"]) }
    attempt("admit party-9 [kim]") { _ = try queue.admit("party-9", ["kim"]) }
    attempt("mark_ready zoe") { _ = try queue.markReady("zoe") }
    attempt("party-8.mark_ready zoe") {
        guard let group = queue.groupOf("kim") else { return }
        _ = try group.markReady("zoe")
    }
    attempt("mark_group_ready party-9") { _ = try queue.markGroupReady("party-9") }
    attempt("cancel party-9") { _ = try queue.cancel("party-9") }
}

do {
    try strictOrderDemo()
    print("")
    try relaxedOrderDemo()
    print("")
    try cancelAndClearDemo()
    print("")
    errorDemo()
} catch {
    print(error)
}
