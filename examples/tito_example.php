<?php
// Together In Together Out - PHP example.
//
// Run: php examples/tito_example.php

declare(strict_types=1);

/** Minimal strict-order (head-of-line FIFO) TITO queue. */
final class TitoQueue
{
    /** @var list<string> */
    private array $order = [];
    /** @var array<string, array<string, bool>> */
    private array $groups = [];
    /** @var array<string, string> */
    private array $groupOf = [];

    /** @param list<string> $members */
    public function admit(string $groupId, array $members): void
    {
        if ($members === []) {
            throw new InvalidArgumentException('a group must contain at least one member');
        }
        if (isset($this->groups[$groupId])) {
            throw new InvalidArgumentException("duplicate group id: $groupId");
        }
        $ready = [];
        foreach ($members as $member) {
            if (isset($this->groupOf[$member]) || isset($ready[$member])) {
                throw new InvalidArgumentException("duplicate member: $member");
            }
            $ready[$member] = false;
        }
        foreach ($members as $member) {
            $this->groupOf[$member] = $groupId;
        }
        $this->groups[$groupId] = $ready;
        $this->order[] = $groupId;
    }

    public function markReady(string $member): void
    {
        if (!isset($this->groupOf[$member])) {
            throw new InvalidArgumentException("unknown member: $member");
        }
        $this->groups[$this->groupOf[$member]][$member] = true;
    }

    /**
     * Release the head group, or null while it is not fully ready.
     *
     * @return array{0: string, 1: list<string>}|null
     */
    public function release(): ?array
    {
        if ($this->order === []) {
            return null;
        }
        $groupId = $this->order[0];
        $ready = $this->groups[$groupId];
        foreach ($ready as $isReady) {
            if (!$isReady) {
                return null;
            }
        }
        array_shift($this->order);
        unset($this->groups[$groupId]);
        $members = array_keys($ready);
        foreach ($members as $member) {
            unset($this->groupOf[$member]);
        }
        return [$groupId, $members];
    }
}

$queue = new TitoQueue();

$queue->admit('party-1', ['ann', 'bob']);
echo "admit party-1: ann, bob\n";
$queue->admit('party-2', ['cy']);
echo "admit party-2: cy\n";

foreach (['ann', 'bob', 'cy'] as $member) {
    $queue->markReady($member);
    echo "ready $member\n";
    $released = $queue->release();
    if ($released === null) {
        echo "release -> waiting\n";
    } else {
        [$groupId, $members] = $released;
        echo "release -> $groupId [" . implode(' ', $members) . "]\n";
    }
}
