// Together In Together Out - C# example.
//
// Run: dotnet run --project examples/csharp

using System;
using System.Collections.Generic;
using System.Linq;

namespace TitoExample;

/// <summary>A group released as a whole.</summary>
public sealed record Released(string GroupId, IReadOnlyList<string> Members);

/// <summary>Minimal strict-order (head-of-line FIFO) TITO queue.</summary>
public sealed class TitoQueue
{
    private readonly Queue<string> _order = new();
    private readonly Dictionary<string, Dictionary<string, bool>> _groups = new();
    private readonly Dictionary<string, string> _groupOf = new();

    public void Admit(string groupId, IReadOnlyList<string> members)
    {
        if (members.Count == 0)
        {
            throw new ArgumentException("a group must contain at least one member", nameof(members));
        }

        if (_groups.ContainsKey(groupId))
        {
            throw new ArgumentException($"duplicate group id: {groupId}", nameof(groupId));
        }

        var ready = new Dictionary<string, bool>();
        foreach (var member in members)
        {
            if (_groupOf.ContainsKey(member) || ready.ContainsKey(member))
            {
                throw new ArgumentException($"duplicate member: {member}", nameof(members));
            }

            ready[member] = false;
        }

        foreach (var member in members)
        {
            _groupOf[member] = groupId;
        }

        _groups[groupId] = ready;
        _order.Enqueue(groupId);
    }

    public void MarkReady(string member)
    {
        if (!_groupOf.TryGetValue(member, out var groupId))
        {
            throw new ArgumentException($"unknown member: {member}", nameof(member));
        }

        _groups[groupId][member] = true;
    }

    /// <summary>Releases the head group, or null while it is not fully ready.</summary>
    public Released? Release()
    {
        if (!_order.TryPeek(out var groupId))
        {
            return null;
        }

        var ready = _groups[groupId];
        if (ready.Values.Any(isReady => !isReady))
        {
            return null;
        }

        _order.Dequeue();
        _groups.Remove(groupId);
        var members = ready.Keys.ToList();
        foreach (var member in members)
        {
            _groupOf.Remove(member);
        }

        return new Released(groupId, members);
    }
}

public static class Program
{
    public static void Main()
    {
        var queue = new TitoQueue();

        queue.Admit("party-1", new[] { "ann", "bob" });
        Console.WriteLine("admit party-1: ann, bob");
        queue.Admit("party-2", new[] { "cy" });
        Console.WriteLine("admit party-2: cy");

        foreach (var member in new[] { "ann", "bob", "cy" })
        {
            queue.MarkReady(member);
            Console.WriteLine($"ready {member}");
            var released = queue.Release();
            if (released is null)
            {
                Console.WriteLine("release -> waiting");
            }
            else
            {
                Console.WriteLine($"release -> {released.GroupId} [{string.Join(' ', released.Members)}]");
            }
        }
    }
}
