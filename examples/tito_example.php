<?php
// Together In Together Out - PHP example.
//
// Run: php examples/tito_example.php

declare(strict_types=1);

/** Raised when an operation would violate the TITO invariants. */
final class TitoError extends RuntimeException
{
}

/**
 * A set of members that entered the queue together.
 *
 * A group is only ever released as a whole: it departs when, and only
 * when, all of its members have been marked ready.
 */
final class Group
{
    public string $groupId;
    /** @var list<string> */
    public array $members;
    /** @var array<string, bool> */
    private array $ready = [];
    private int $tally = 0;

    /** @param list<string> $members */
    public function __construct(string $groupId, array $members)
    {
        if ($members === []) {
            throw new TitoError("group $groupId must contain at least one member");
        }
        // Keyed by member so membership is O(1) and the ready flag rides along;
        // insertion order is the admission order the demo prints.
        $ready = [];
        foreach ($members as $member) {
            $ready[$member] = false;
        }
        if (count($ready) !== count($members)) {
            throw new TitoError("group $groupId contains duplicate members");
        }
        $this->groupId = $groupId;
        $this->members = $members;
        $this->ready = $ready;
    }

    /**
     * Members already marked ready, in admission order.
     *
     * @return list<string>
     */
    public function readyMembers(): array
    {
        return array_values(array_filter($this->members, fn (string $m): bool => $this->ready[$m]));
    }

    /**
     * Members not yet marked ready, in admission order.
     *
     * @return list<string>
     */
    public function waitingMembers(): array
    {
        return array_values(array_filter($this->members, fn (string $m): bool => !$this->ready[$m]));
    }

    /** How many members have been marked ready. */
    public function readyCount(): int
    {
        return $this->tally;
    }

    /** True once every member of the group is ready to depart. */
    public function isReady(): bool
    {
        return $this->tally === count($this->members);
    }

    /** Mark one member ready. Returns true if the whole group is ready. */
    public function markReady(string $member): bool
    {
        if (!array_key_exists($member, $this->ready)) {
            throw new TitoError("$member is not a member of group $this->groupId");
        }
        if (!$this->ready[$member]) {
            $this->ready[$member] = true;
            $this->tally++;
        }
        return $this->isReady();
    }

    public function size(): int
    {
        return count($this->members);
    }

    public function contains(string $member): bool
    {
        return array_key_exists($member, $this->ready);
    }

    public function __toString(): string
    {
        return $this->groupId . ' [' . implode(' ', $this->members) . ']';
    }
}

/**
 * A queue that admits and releases members group by group.
 *
 * strictOrder=true (the default) is head-of-line FIFO: only the oldest
 * waiting group may depart. strictOrder=false lets any fully ready group
 * depart, still oldest first, so a waiting group does not block the ready
 * groups behind it.
 */
final class TitoQueue
{
    public bool $strictOrder;
    /** @var array<string, Group> */
    private array $groups = [];
    /** @var array<string, string> */
    private array $memberIndex = [];

    public function __construct(bool $strictOrder = true)
    {
        $this->strictOrder = $strictOrder;
    }

    /** Admit members as one group. Returns the admitted group. */
    public function admit(string $groupId, array $members): Group
    {
        $group = new Group($groupId, $members);
        if (isset($this->groups[$groupId])) {
            throw new TitoError("group $groupId is already in the queue");
        }
        $queued = array_values(array_filter(
            $group->members,
            fn (string $m): bool => isset($this->memberIndex[$m])
        ));
        if ($queued !== []) {
            throw new TitoError('members already in the queue: ' . implode(' ', $queued));
        }
        $this->groups[$groupId] = $group;
        foreach ($group->members as $member) {
            $this->memberIndex[$member] = $groupId;
        }
        return $group;
    }

    /** Mark a queued member ready. Returns true if its group is ready. */
    public function markReady(string $member): bool
    {
        $group = $this->groupOf($member);
        if ($group === null) {
            throw new TitoError("$member is not in the queue");
        }
        return $group->markReady($member);
    }

    /** Mark every member of a queued group ready. */
    public function markGroupReady(string $groupId): bool
    {
        $group = $this->groups[$groupId] ?? null;
        if ($group === null) {
            throw new TitoError("group $groupId is not in the queue");
        }
        foreach ($group->members as $member) {
            $group->markReady($member);
        }
        return true;
    }

    /** The group a queued member belongs to, or null if not queued. */
    public function groupOf(string $member): ?Group
    {
        $groupId = $this->memberIndex[$member] ?? null;
        if ($groupId === null) {
            return null;
        }
        return $this->groups[$groupId];
    }

    /** The next group that would be released, without releasing it. */
    public function peek(): ?Group
    {
        foreach ($this->groups as $group) {
            if ($group->isReady()) {
                return $group;
            }
            if ($this->strictOrder) {
                // Head of the line blocks every group behind it.
                return null;
            }
        }
        return null;
    }

    /** Release the next fully ready group, or null if none can depart. */
    public function release(): ?Group
    {
        $group = $this->peek();
        if ($group === null) {
            return null;
        }
        $this->remove($group);
        return $group;
    }

    /**
     * Release every group that can currently depart, in order.
     *
     * @return list<Group>
     */
    public function releaseAll(): array
    {
        $released = [];
        while (($group = $this->release()) !== null) {
            $released[] = $group;
        }
        return $released;
    }

    /** Withdraw a waiting group, ready or not, and return it. */
    public function cancel(string $groupId): Group
    {
        $group = $this->groups[$groupId] ?? null;
        if ($group === null) {
            throw new TitoError("group $groupId is not in the queue");
        }
        $this->remove($group);
        return $group;
    }

    /**
     * Withdraw every waiting group, in arrival order, and return them.
     *
     * @return list<Group>
     */
    public function clear(): array
    {
        $cleared = array_values($this->groups);
        $this->groups = [];
        $this->memberIndex = [];
        return $cleared;
    }

    /**
     * Waiting groups, in arrival order.
     *
     * @return list<Group>
     */
    public function groups(): array
    {
        return array_values($this->groups);
    }

    public function size(): int
    {
        return count($this->groups);
    }

    public function contains(string $member): bool
    {
        return isset($this->memberIndex[$member]);
    }

    private function remove(Group $group): void
    {
        unset($this->groups[$group->groupId]);
        foreach ($group->members as $member) {
            unset($this->memberIndex[$member]);
        }
    }

    public function __toString(): string
    {
        return sprintf(
            'TitoQueue(strictOrder=%s, groups=%d)',
            $this->strictOrder ? 'true' : 'false',
            count($this->groups)
        );
    }
}

/** Format a boolean the same way in every example language. */
function flag(bool $value): string
{
    return $value ? 'true' : 'false';
}

/** Format an optional group, as returned by peek() and release(). */
function show(?Group $group): string
{
    return $group === null ? 'waiting' : (string) $group;
}

/**
 * Format the group lists returned by releaseAll() and clear().
 *
 * @param list<Group> $groups
 */
function showAll(array $groups): string
{
    if ($groups === []) {
        return 'none';
    }
    return implode(', ', array_map(fn (Group $g): string => (string) $g, $groups));
}

/**
 * Format the group ids of the waiting groups.
 *
 * @param list<Group> $groups
 */
function showIds(array $groups): string
{
    if ($groups === []) {
        return 'none';
    }
    return implode(' ', array_map(fn (Group $g): string => $g->groupId, $groups));
}

/** Head-of-line FIFO: party-2 waits behind party-1 until it departs. */
function strictOrderDemo(): void
{
    echo "-- strict order --\n";
    $queue = new TitoQueue();
    echo 'admit ' . $queue->admit('party-1', ['ann', 'bob']) . "\n";
    echo 'admit ' . $queue->admit('party-2', ['cy']) . "\n";
    echo 'len ' . $queue->size() . ', groups ' . showIds($queue->groups()) . "\n";
    echo 'contains ann ' . flag($queue->contains('ann')) . ', contains zoe ' . flag($queue->contains('zoe')) . "\n";

    $party1 = $queue->groupOf('bob');
    echo 'group_of bob -> ' . $party1->groupId . "\n";
    echo 'party-1: size ' . $party1->size() . ', contains ann ' . flag($party1->contains('ann'))
        . ', contains zoe ' . flag($party1->contains('zoe')) . "\n";

    echo 'mark_ready ann -> group ready ' . flag($queue->markReady('ann')) . "\n";
    echo 'party-1: ' . $party1->readyCount() . '/' . $party1->size()
        . ' ready [' . implode(' ', $party1->readyMembers()) . ']'
        . ' waiting [' . implode(' ', $party1->waitingMembers()) . ']'
        . ' is_ready ' . flag($party1->isReady()) . "\n";
    echo 'peek -> ' . show($queue->peek()) . "\n";
    echo 'release -> ' . show($queue->release()) . "\n";

    echo 'party-1.mark_ready bob -> group ready ' . flag($party1->markReady('bob')) . "\n";
    echo 'party-1: ' . $party1->readyCount() . '/' . $party1->size()
        . ' ready [' . implode(' ', $party1->readyMembers()) . ']'
        . ' waiting [' . implode(' ', $party1->waitingMembers()) . ']'
        . ' is_ready ' . flag($party1->isReady()) . "\n";
    echo 'peek -> ' . show($queue->peek()) . "\n";
    echo 'release -> ' . show($queue->release()) . "\n";

    echo 'mark_group_ready party-2 -> ' . flag($queue->markGroupReady('party-2')) . "\n";
    echo 'release_all -> ' . showAll($queue->releaseAll()) . "\n";
    echo 'len ' . $queue->size() . "\n";
}

/** Without strict order, ready party-4 leaves ahead of waiting party-3. */
function relaxedOrderDemo(): void
{
    echo "-- relaxed order --\n";
    $queue = new TitoQueue(false);
    echo 'strict_order ' . flag($queue->strictOrder) . "\n";
    echo 'admit ' . $queue->admit('party-3', ['dee', 'eli']) . "\n";
    echo 'admit ' . $queue->admit('party-4', ['fay']) . "\n";

    echo 'mark_group_ready party-4 -> ' . flag($queue->markGroupReady('party-4')) . "\n";
    echo 'peek -> ' . show($queue->peek()) . "\n";
    echo 'release -> ' . show($queue->release()) . "\n";

    echo 'mark_ready dee -> group ready ' . flag($queue->markReady('dee')) . "\n";
    echo 'release -> ' . show($queue->release()) . "\n";
    echo 'mark_ready eli -> group ready ' . flag($queue->markReady('eli')) . "\n";
    echo 'release_all -> ' . showAll($queue->releaseAll()) . "\n";
    echo 'len ' . $queue->size() . "\n";
}

/** Cancelling is the only way a group leaves before it is fully ready. */
function cancelAndClearDemo(): void
{
    echo "-- cancel and clear --\n";
    $queue = new TitoQueue();
    echo 'admit ' . $queue->admit('party-5', ['gil', 'hal']) . "\n";
    echo 'admit ' . $queue->admit('party-6', ['ivy']) . "\n";
    echo 'admit ' . $queue->admit('party-7', ['jay']) . "\n";

    echo 'mark_ready gil -> group ready ' . flag($queue->markReady('gil')) . "\n";
    $cancelled = $queue->cancel('party-5');
    echo 'cancel party-5 -> ' . $cancelled . ' ' . $cancelled->readyCount() . '/' . $cancelled->size() . " ready\n";
    echo 'groups ' . showIds($queue->groups()) . "\n";
    echo 'clear -> ' . showAll($queue->clear()) . "\n";
    echo 'len ' . $queue->size() . ', contains ivy ' . flag($queue->contains('ivy')) . "\n";
}

/**
 * Run an operation that must fail, and print the reported reason.
 *
 * @param callable():void $action
 */
function attempt(string $label, callable $action): void
{
    try {
        $action();
    } catch (TitoError $error) {
        echo "$label -> {$error->getMessage()}\n";
        return;
    }
    echo "$label -> no error\n";
}

/** Every operation that would break the TITO invariants is rejected. */
function errorDemo(): void
{
    echo "-- errors --\n";
    $queue = new TitoQueue();
    echo 'admit ' . $queue->admit('party-8', ['kim']) . "\n";

    attempt('admit party-8 [kim]', fn () => $queue->admit('party-8', ['kim']));
    attempt('admit party-9 []', fn () => $queue->admit('party-9', []));
    attempt('admit party-9 [jay jay]', fn () => $queue->admit('party-9', ['jay', 'jay']));
    attempt('admit party-9 [kim]', fn () => $queue->admit('party-9', ['kim']));
    attempt('mark_ready zoe', fn () => $queue->markReady('zoe'));
    attempt('party-8.mark_ready zoe', fn () => $queue->groupOf('kim')->markReady('zoe'));
    attempt('mark_group_ready party-9', fn () => $queue->markGroupReady('party-9'));
    attempt('cancel party-9', fn () => $queue->cancel('party-9'));
}

function main(): void
{
    strictOrderDemo();
    echo "\n";
    relaxedOrderDemo();
    echo "\n";
    cancelAndClearDemo();
    echo "\n";
    errorDemo();
}

main();
