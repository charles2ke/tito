// Together In Together Out - C# example.
//
// Run: dotnet run --project examples/csharp

using System;
using System.Collections.Generic;
using System.Linq;

namespace TitoExample;

/// <summary>Raised when an operation would violate the TITO invariants.</summary>
public sealed class TitoException : Exception
{
    public TitoException(string message) : base(message)
    {
    }
}

/// <summary>
/// A set of members that entered the queue together. A group is only ever
/// released as a whole: it departs once every member has been marked ready.
/// </summary>
public sealed class Group
{
    private readonly List<string> _members;
    private readonly Dictionary<string, bool> _ready;
    private int _readyCount;

    public Group(string groupId, IEnumerable<string> members)
    {
        var memberList = members.ToList();
        if (memberList.Count == 0)
        {
            throw new TitoException($"group {groupId} must contain at least one member");
        }

        var ready = new Dictionary<string, bool>();
        foreach (var member in memberList)
        {
            ready[member] = false;
        }

        if (ready.Count != memberList.Count)
        {
            throw new TitoException($"group {groupId} contains duplicate members");
        }

        GroupId = groupId;
        _members = memberList;
        _ready = ready;
    }

    public string GroupId { get; }

    /// <summary>The members of this group, in the order they were admitted.</summary>
    public IReadOnlyList<string> Members => _members;

    /// <summary>Members already marked ready, in admission order.</summary>
    public IReadOnlyList<string> ReadyMembers => _members.Where(member => _ready[member]).ToList();

    /// <summary>Members not yet marked ready, in admission order.</summary>
    public IReadOnlyList<string> WaitingMembers => _members.Where(member => !_ready[member]).ToList();

    /// <summary>How many members have been marked ready.</summary>
    public int ReadyCount => _readyCount;

    /// <summary>True once every member of the group is ready to depart.</summary>
    public bool IsReady => _readyCount == _members.Count;

    /// <summary>Number of members admitted with the group.</summary>
    public int Count => _members.Count;

    /// <summary>Mark one member ready. Returns true if the whole group is ready.</summary>
    public bool MarkReady(string member)
    {
        if (!_ready.TryGetValue(member, out var already))
        {
            throw new TitoException($"{member} is not a member of group {GroupId}");
        }

        if (!already)
        {
            _ready[member] = true;
            _readyCount++;
        }

        return IsReady;
    }

    public bool Contains(string member) => _ready.ContainsKey(member);

    public override string ToString() => $"{GroupId} [{string.Join(" ", _members)}]";
}

/// <summary>
/// A queue that admits and releases members group by group. Strict order (the
/// default) is head-of-line FIFO: only the oldest waiting group may depart.
/// Relaxed order lets any fully ready group depart, oldest first, so a waiting
/// group does not block the ready groups behind it.
/// </summary>
public sealed class TitoQueue
{
    private readonly List<Group> _order = new();
    private readonly Dictionary<string, Group> _byId = new();
    private readonly Dictionary<string, string> _memberIndex = new();

    public TitoQueue(bool strictOrder = true)
    {
        StrictOrder = strictOrder;
    }

    /// <summary>The ordering policy: head-of-line FIFO when true.</summary>
    public bool StrictOrder { get; }

    /// <summary>Admit members as one group. Returns the admitted group.</summary>
    public Group Admit(string groupId, IEnumerable<string> members)
    {
        var group = new Group(groupId, members);
        if (_byId.ContainsKey(groupId))
        {
            throw new TitoException($"group {groupId} is already in the queue");
        }

        var queued = group.Members.Where(member => _memberIndex.ContainsKey(member)).ToList();
        if (queued.Count > 0)
        {
            throw new TitoException($"members already in the queue: {string.Join(" ", queued)}");
        }

        _byId[groupId] = group;
        _order.Add(group);
        foreach (var member in group.Members)
        {
            _memberIndex[member] = groupId;
        }

        return group;
    }

    /// <summary>Mark a queued member ready. Returns true if its group is ready.</summary>
    public bool MarkReady(string member)
    {
        var group = GroupOf(member);
        if (group is null)
        {
            throw new TitoException($"{member} is not in the queue");
        }

        return group.MarkReady(member);
    }

    /// <summary>Mark every member of a queued group ready.</summary>
    public bool MarkGroupReady(string groupId)
    {
        if (!_byId.TryGetValue(groupId, out var group))
        {
            throw new TitoException($"group {groupId} is not in the queue");
        }

        foreach (var member in group.Members)
        {
            group.MarkReady(member);
        }

        return true;
    }

    /// <summary>The group a queued member belongs to, or null if not queued.</summary>
    public Group? GroupOf(string member)
    {
        return _memberIndex.TryGetValue(member, out var groupId) ? _byId[groupId] : null;
    }

    /// <summary>The next group that would be released, without releasing it.</summary>
    public Group? Peek()
    {
        foreach (var group in _order)
        {
            if (group.IsReady)
            {
                return group;
            }

            if (StrictOrder)
            {
                // Head of the line blocks every group behind it.
                return null;
            }
        }

        return null;
    }

    /// <summary>Release the next fully ready group, or null if none can depart.</summary>
    public Group? Release()
    {
        var group = Peek();
        if (group is null)
        {
            return null;
        }

        Remove(group);
        return group;
    }

    /// <summary>Release every group that can currently depart, in order.</summary>
    public List<Group> ReleaseAll()
    {
        var released = new List<Group>();
        while (true)
        {
            var group = Release();
            if (group is null)
            {
                return released;
            }

            released.Add(group);
        }
    }

    /// <summary>Withdraw a waiting group, ready or not, and return it.</summary>
    public Group Cancel(string groupId)
    {
        if (!_byId.TryGetValue(groupId, out var group))
        {
            throw new TitoException($"group {groupId} is not in the queue");
        }

        Remove(group);
        return group;
    }

    /// <summary>Withdraw every waiting group, in arrival order, and return them.</summary>
    public List<Group> Clear()
    {
        var cleared = new List<Group>(_order);
        _order.Clear();
        _byId.Clear();
        _memberIndex.Clear();
        return cleared;
    }

    /// <summary>Waiting groups, in arrival order.</summary>
    public IReadOnlyList<Group> Groups => new List<Group>(_order);

    /// <summary>Number of waiting groups.</summary>
    public int Count => _order.Count;

    public bool Contains(string member) => _memberIndex.ContainsKey(member);

    private void Remove(Group group)
    {
        _order.Remove(group);
        _byId.Remove(group.GroupId);
        foreach (var member in group.Members)
        {
            _memberIndex.Remove(member);
        }
    }
}

public static class Program
{
    public static void Main()
    {
        StrictOrderDemo();
        Console.WriteLine();
        RelaxedOrderDemo();
        Console.WriteLine();
        CancelAndClearDemo();
        Console.WriteLine();
        ErrorDemo();
    }

    // Head-of-line FIFO: party-2 waits behind party-1 until it departs.
    private static void StrictOrderDemo()
    {
        Console.WriteLine("-- strict order --");
        var queue = new TitoQueue();
        Console.WriteLine($"admit {queue.Admit("party-1", new[] { "ann", "bob" })}");
        Console.WriteLine($"admit {queue.Admit("party-2", new[] { "cy" })}");
        Console.WriteLine($"len {queue.Count}, groups {ShowIds(queue.Groups)}");
        Console.WriteLine($"contains ann {Flag(queue.Contains("ann"))}, contains zoe {Flag(queue.Contains("zoe"))}");

        var party1 = queue.GroupOf("bob")!;
        Console.WriteLine($"group_of bob -> {party1.GroupId}");
        Console.WriteLine($"party-1: size {party1.Count}, contains ann {Flag(party1.Contains("ann"))}, contains zoe {Flag(party1.Contains("zoe"))}");

        Console.WriteLine($"mark_ready ann -> group ready {Flag(queue.MarkReady("ann"))}");
        Console.WriteLine($"party-1: {party1.ReadyCount}/{party1.Count} ready [{string.Join(" ", party1.ReadyMembers)}] waiting [{string.Join(" ", party1.WaitingMembers)}] is_ready {Flag(party1.IsReady)}");
        Console.WriteLine($"peek -> {Show(queue.Peek())}");
        Console.WriteLine($"release -> {Show(queue.Release())}");

        Console.WriteLine($"party-1.mark_ready bob -> group ready {Flag(party1.MarkReady("bob"))}");
        Console.WriteLine($"party-1: {party1.ReadyCount}/{party1.Count} ready [{string.Join(" ", party1.ReadyMembers)}] waiting [{string.Join(" ", party1.WaitingMembers)}] is_ready {Flag(party1.IsReady)}");
        Console.WriteLine($"peek -> {Show(queue.Peek())}");
        Console.WriteLine($"release -> {Show(queue.Release())}");

        Console.WriteLine($"mark_group_ready party-2 -> {Flag(queue.MarkGroupReady("party-2"))}");
        Console.WriteLine($"release_all -> {ShowAll(queue.ReleaseAll())}");
        Console.WriteLine($"len {queue.Count}");
    }

    // Without strict order, ready party-4 leaves ahead of waiting party-3.
    private static void RelaxedOrderDemo()
    {
        Console.WriteLine("-- relaxed order --");
        var queue = new TitoQueue(strictOrder: false);
        Console.WriteLine($"strict_order {Flag(queue.StrictOrder)}");
        Console.WriteLine($"admit {queue.Admit("party-3", new[] { "dee", "eli" })}");
        Console.WriteLine($"admit {queue.Admit("party-4", new[] { "fay" })}");

        Console.WriteLine($"mark_group_ready party-4 -> {Flag(queue.MarkGroupReady("party-4"))}");
        Console.WriteLine($"peek -> {Show(queue.Peek())}");
        Console.WriteLine($"release -> {Show(queue.Release())}");

        Console.WriteLine($"mark_ready dee -> group ready {Flag(queue.MarkReady("dee"))}");
        Console.WriteLine($"release -> {Show(queue.Release())}");
        Console.WriteLine($"mark_ready eli -> group ready {Flag(queue.MarkReady("eli"))}");
        Console.WriteLine($"release_all -> {ShowAll(queue.ReleaseAll())}");
        Console.WriteLine($"len {queue.Count}");
    }

    // Cancelling is the only way a group leaves before it is fully ready.
    private static void CancelAndClearDemo()
    {
        Console.WriteLine("-- cancel and clear --");
        var queue = new TitoQueue();
        Console.WriteLine($"admit {queue.Admit("party-5", new[] { "gil", "hal" })}");
        Console.WriteLine($"admit {queue.Admit("party-6", new[] { "ivy" })}");
        Console.WriteLine($"admit {queue.Admit("party-7", new[] { "jay" })}");

        Console.WriteLine($"mark_ready gil -> group ready {Flag(queue.MarkReady("gil"))}");
        var cancelled = queue.Cancel("party-5");
        Console.WriteLine($"cancel party-5 -> {cancelled} {cancelled.ReadyCount}/{cancelled.Count} ready");
        Console.WriteLine($"groups {ShowIds(queue.Groups)}");
        Console.WriteLine($"clear -> {ShowAll(queue.Clear())}");
        Console.WriteLine($"len {queue.Count}, contains ivy {Flag(queue.Contains("ivy"))}");
    }

    // Every operation that would break the TITO invariants is rejected.
    private static void ErrorDemo()
    {
        Console.WriteLine("-- errors --");
        var queue = new TitoQueue();
        Console.WriteLine($"admit {queue.Admit("party-8", new[] { "kim" })}");

        Attempt("admit party-8 [kim]", () => queue.Admit("party-8", new[] { "kim" }));
        Attempt("admit party-9 []", () => queue.Admit("party-9", Array.Empty<string>()));
        Attempt("admit party-9 [jay jay]", () => queue.Admit("party-9", new[] { "jay", "jay" }));
        Attempt("admit party-9 [kim]", () => queue.Admit("party-9", new[] { "kim" }));
        Attempt("mark_ready zoe", () => queue.MarkReady("zoe"));
        Attempt("party-8.mark_ready zoe", () => queue.GroupOf("kim")!.MarkReady("zoe"));
        Attempt("mark_group_ready party-9", () => queue.MarkGroupReady("party-9"));
        Attempt("cancel party-9", () => queue.Cancel("party-9"));
    }

    // Format a boolean the same way in every example language.
    private static string Flag(bool value) => value ? "true" : "false";

    // Format an optional group, as returned by Peek() and Release().
    private static string Show(Group? group) => group is null ? "waiting" : group.ToString();

    // Format the group lists returned by ReleaseAll() and Clear().
    private static string ShowAll(IReadOnlyList<Group> groups) =>
        groups.Count == 0 ? "none" : string.Join(", ", groups.Select(group => group.ToString()));

    // Format the group ids of the waiting groups.
    private static string ShowIds(IReadOnlyList<Group> groups) =>
        groups.Count == 0 ? "none" : string.Join(" ", groups.Select(group => group.GroupId));

    // Run an operation that must fail, and print the reported reason.
    private static void Attempt(string label, Action action)
    {
        try
        {
            action();
            Console.WriteLine($"{label} -> no error");
        }
        catch (TitoException error)
        {
            Console.WriteLine($"{label} -> {error.Message}");
        }
    }
}
