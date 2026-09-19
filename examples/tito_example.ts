// Together In Together Out - TypeScript example.
//
// Run: tsc --strict --target es2020 --outDir /tmp/tito examples/tito_example.ts
//      && node /tmp/tito/tito_example.js

/** Raised when an operation would violate the TITO invariants. */
class TitoError extends Error {}

/**
 * A set of members that entered the queue together.
 *
 * A group is only ever released as a whole: it departs when, and only
 * when, all of its members have been marked ready.
 */
class Group {
  readonly groupId: string;
  readonly members: string[];
  private readonly ready: Map<string, boolean>;
  private tally = 0;

  constructor(groupId: string, members: readonly string[]) {
    const memberList = [...members];
    if (memberList.length === 0) {
      throw new TitoError(`group ${groupId} must contain at least one member`);
    }
    // A Map answers membership and carries the ready flag in one slot, and
    // preserves the admission order the demo prints members in.
    const ready = new Map<string, boolean>();
    for (const member of memberList) {
      ready.set(member, false);
    }
    if (ready.size !== memberList.length) {
      throw new TitoError(`group ${groupId} contains duplicate members`);
    }
    this.groupId = groupId;
    this.members = memberList;
    this.ready = ready;
  }

  /** Members already marked ready, in admission order. */
  get readyMembers(): string[] {
    return this.members.filter((member) => this.ready.get(member));
  }

  /** Members not yet marked ready, in admission order. */
  get waitingMembers(): string[] {
    return this.members.filter((member) => !this.ready.get(member));
  }

  /** How many members have been marked ready. */
  get readyCount(): number {
    return this.tally;
  }

  /** True once every member of the group is ready to depart. */
  get isReady(): boolean {
    return this.tally === this.members.length;
  }

  /** Mark one member ready. Returns true if the whole group is ready. */
  markReady(member: string): boolean {
    if (!this.ready.has(member)) {
      throw new TitoError(`${member} is not a member of group ${this.groupId}`);
    }
    if (!this.ready.get(member)) {
      this.ready.set(member, true);
      this.tally += 1;
    }
    return this.isReady;
  }

  get size(): number {
    return this.members.length;
  }

  contains(member: string): boolean {
    return this.ready.has(member);
  }

  toString(): string {
    return `${this.groupId} [${this.members.join(' ')}]`;
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
class TitoQueue {
  readonly strictOrder: boolean;
  private readonly groupsById = new Map<string, Group>();
  private readonly memberIndex = new Map<string, string>();

  constructor(strictOrder = true) {
    this.strictOrder = strictOrder;
  }

  /** Admit members as one group. Returns the admitted group. */
  admit(groupId: string, members: readonly string[]): Group {
    const group = new Group(groupId, members);
    if (this.groupsById.has(groupId)) {
      throw new TitoError(`group ${groupId} is already in the queue`);
    }
    const queued = group.members.filter((member) => this.memberIndex.has(member));
    if (queued.length > 0) {
      throw new TitoError(`members already in the queue: ${queued.join(' ')}`);
    }
    this.groupsById.set(groupId, group);
    for (const member of group.members) {
      this.memberIndex.set(member, groupId);
    }
    return group;
  }

  /** Mark a queued member ready. Returns true if its group is ready. */
  markReady(member: string): boolean {
    const group = this.groupOf(member);
    if (group === null) {
      throw new TitoError(`${member} is not in the queue`);
    }
    return group.markReady(member);
  }

  /** Mark every member of a queued group ready. */
  markGroupReady(groupId: string): boolean {
    const group = this.groupsById.get(groupId);
    if (group === undefined) {
      throw new TitoError(`group ${groupId} is not in the queue`);
    }
    for (const member of group.members) {
      group.markReady(member);
    }
    return true;
  }

  /** The group a queued member belongs to, or null if not queued. */
  groupOf(member: string): Group | null {
    const groupId = this.memberIndex.get(member);
    if (groupId === undefined) {
      return null;
    }
    return this.groupsById.get(groupId) ?? null;
  }

  /** The next group that would be released, without releasing it. */
  peek(): Group | null {
    for (const group of this.groupsById.values()) {
      if (group.isReady) {
        return group;
      }
      if (this.strictOrder) {
        // Head of the line blocks every group behind it.
        return null;
      }
    }
    return null;
  }

  /** Release the next fully ready group, or null if none can depart. */
  release(): Group | null {
    const group = this.peek();
    if (group === null) {
      return null;
    }
    this.remove(group);
    return group;
  }

  /** Release every group that can currently depart, in order. */
  releaseAll(): Group[] {
    const released: Group[] = [];
    for (;;) {
      const group = this.release();
      if (group === null) {
        return released;
      }
      released.push(group);
    }
  }

  /** Withdraw a waiting group, ready or not, and return it. */
  cancel(groupId: string): Group {
    const group = this.groupsById.get(groupId);
    if (group === undefined) {
      throw new TitoError(`group ${groupId} is not in the queue`);
    }
    this.remove(group);
    return group;
  }

  /** Withdraw every waiting group, in arrival order, and return them. */
  clear(): Group[] {
    const cleared = [...this.groupsById.values()];
    this.groupsById.clear();
    this.memberIndex.clear();
    return cleared;
  }

  /** Waiting groups, in arrival order. */
  get groups(): Group[] {
    return [...this.groupsById.values()];
  }

  get size(): number {
    return this.groupsById.size;
  }

  contains(member: string): boolean {
    return this.memberIndex.has(member);
  }

  private remove(group: Group): void {
    this.groupsById.delete(group.groupId);
    for (const member of group.members) {
      this.memberIndex.delete(member);
    }
  }

  toString(): string {
    return `TitoQueue(strictOrder=${this.strictOrder}, groups=${this.groupsById.size})`;
  }
}

/** Format a boolean the same way in every example language. */
function flag(value: boolean): string {
  return value ? 'true' : 'false';
}

/** Format an optional group, as returned by peek() and release(). */
function show(group: Group | null): string {
  return group === null ? 'waiting' : `${group}`;
}

/** Format the group lists returned by releaseAll() and clear(). */
function showAll(groups: Group[]): string {
  if (groups.length === 0) {
    return 'none';
  }
  return groups.map((group) => `${group}`).join(', ');
}

/** Format the group ids of the waiting groups. */
function showIds(groups: Group[]): string {
  if (groups.length === 0) {
    return 'none';
  }
  return groups.map((group) => group.groupId).join(' ');
}

/** Head-of-line FIFO: party-2 waits behind party-1 until it departs. */
function strictOrderDemo(): void {
  console.log('-- strict order --');
  const queue = new TitoQueue();
  console.log(`admit ${queue.admit('party-1', ['ann', 'bob'])}`);
  console.log(`admit ${queue.admit('party-2', ['cy'])}`);
  console.log(`len ${queue.size}, groups ${showIds(queue.groups)}`);
  console.log(`contains ann ${flag(queue.contains('ann'))}, contains zoe ${flag(queue.contains('zoe'))}`);

  const party1 = queue.groupOf('bob')!;
  console.log(`group_of bob -> ${party1.groupId}`);
  console.log(`party-1: size ${party1.size}, contains ann ${flag(party1.contains('ann'))}, `
    + `contains zoe ${flag(party1.contains('zoe'))}`);

  console.log(`mark_ready ann -> group ready ${flag(queue.markReady('ann'))}`);
  console.log(`party-1: ${party1.readyCount}/${party1.size} ready [${party1.readyMembers.join(' ')}] `
    + `waiting [${party1.waitingMembers.join(' ')}] is_ready ${flag(party1.isReady)}`);
  console.log(`peek -> ${show(queue.peek())}`);
  console.log(`release -> ${show(queue.release())}`);

  console.log(`party-1.mark_ready bob -> group ready ${flag(party1.markReady('bob'))}`);
  console.log(`party-1: ${party1.readyCount}/${party1.size} ready [${party1.readyMembers.join(' ')}] `
    + `waiting [${party1.waitingMembers.join(' ')}] is_ready ${flag(party1.isReady)}`);
  console.log(`peek -> ${show(queue.peek())}`);
  console.log(`release -> ${show(queue.release())}`);

  console.log(`mark_group_ready party-2 -> ${flag(queue.markGroupReady('party-2'))}`);
  console.log(`release_all -> ${showAll(queue.releaseAll())}`);
  console.log(`len ${queue.size}`);
}

/** Without strict order, ready party-4 leaves ahead of waiting party-3. */
function relaxedOrderDemo(): void {
  console.log('-- relaxed order --');
  const queue = new TitoQueue(false);
  console.log(`strict_order ${flag(queue.strictOrder)}`);
  console.log(`admit ${queue.admit('party-3', ['dee', 'eli'])}`);
  console.log(`admit ${queue.admit('party-4', ['fay'])}`);

  console.log(`mark_group_ready party-4 -> ${flag(queue.markGroupReady('party-4'))}`);
  console.log(`peek -> ${show(queue.peek())}`);
  console.log(`release -> ${show(queue.release())}`);

  console.log(`mark_ready dee -> group ready ${flag(queue.markReady('dee'))}`);
  console.log(`release -> ${show(queue.release())}`);
  console.log(`mark_ready eli -> group ready ${flag(queue.markReady('eli'))}`);
  console.log(`release_all -> ${showAll(queue.releaseAll())}`);
  console.log(`len ${queue.size}`);
}

/** Cancelling is the only way a group leaves before it is fully ready. */
function cancelAndClearDemo(): void {
  console.log('-- cancel and clear --');
  const queue = new TitoQueue();
  console.log(`admit ${queue.admit('party-5', ['gil', 'hal'])}`);
  console.log(`admit ${queue.admit('party-6', ['ivy'])}`);
  console.log(`admit ${queue.admit('party-7', ['jay'])}`);

  console.log(`mark_ready gil -> group ready ${flag(queue.markReady('gil'))}`);
  const cancelled = queue.cancel('party-5');
  console.log(`cancel party-5 -> ${cancelled} ${cancelled.readyCount}/${cancelled.size} ready`);
  console.log(`groups ${showIds(queue.groups)}`);
  console.log(`clear -> ${showAll(queue.clear())}`);
  console.log(`len ${queue.size}, contains ivy ${flag(queue.contains('ivy'))}`);
}

/** Run an operation that must fail, and print the reported reason. */
function attempt(label: string, action: () => void): void {
  try {
    action();
  } catch (error) {
    if (error instanceof TitoError) {
      console.log(`${label} -> ${error.message}`);
      return;
    }
    throw error;
  }
  console.log(`${label} -> no error`);
}

/** Every operation that would break the TITO invariants is rejected. */
function errorDemo(): void {
  console.log('-- errors --');
  const queue = new TitoQueue();
  console.log(`admit ${queue.admit('party-8', ['kim'])}`);

  attempt('admit party-8 [kim]', () => queue.admit('party-8', ['kim']));
  attempt('admit party-9 []', () => queue.admit('party-9', []));
  attempt('admit party-9 [jay jay]', () => queue.admit('party-9', ['jay', 'jay']));
  attempt('admit party-9 [kim]', () => queue.admit('party-9', ['kim']));
  attempt('mark_ready zoe', () => queue.markReady('zoe'));
  attempt('party-8.mark_ready zoe', () => queue.groupOf('kim')!.markReady('zoe'));
  attempt('mark_group_ready party-9', () => queue.markGroupReady('party-9'));
  attempt('cancel party-9', () => queue.cancel('party-9'));
}

function main(): void {
  strictOrderDemo();
  console.log('');
  relaxedOrderDemo();
  console.log('');
  cancelAndClearDemo();
  console.log('');
  errorDemo();
}

main();
