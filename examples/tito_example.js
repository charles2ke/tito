// Together In Together Out - JavaScript example.
//
// Run: node examples/tito_example.js

'use strict';

/** Raised when an operation would violate the TITO invariants. */
class TitoError extends Error {}

/**
 * A set of members that entered the queue together.
 *
 * A group is only ever released as a whole: it departs when, and only
 * when, all of its members have been marked ready.
 */
class Group {
  constructor(groupId, members) {
    const memberList = [...members];
    if (memberList.length === 0) {
      throw new TitoError(`group ${groupId} must contain at least one member`);
    }
    // A Map answers membership and carries the ready flag in one slot, and
    // preserves the admission order the demo prints members in.
    const ready = new Map();
    for (const member of memberList) {
      ready.set(member, false);
    }
    if (ready.size !== memberList.length) {
      throw new TitoError(`group ${groupId} contains duplicate members`);
    }
    this.groupId = groupId;
    this.members = memberList;
    this._ready = ready;
    this._readyCount = 0;
  }

  /** Members already marked ready, in admission order. */
  get readyMembers() {
    return this.members.filter((member) => this._ready.get(member));
  }

  /** Members not yet marked ready, in admission order. */
  get waitingMembers() {
    return this.members.filter((member) => !this._ready.get(member));
  }

  /** How many members have been marked ready. */
  get readyCount() {
    return this._readyCount;
  }

  /** True once every member of the group is ready to depart. */
  get isReady() {
    return this._readyCount === this.members.length;
  }

  /** Mark one member ready. Returns true if the whole group is ready. */
  markReady(member) {
    if (!this._ready.has(member)) {
      throw new TitoError(`${member} is not a member of group ${this.groupId}`);
    }
    if (!this._ready.get(member)) {
      this._ready.set(member, true);
      this._readyCount += 1;
    }
    return this.isReady;
  }

  get size() {
    return this.members.length;
  }

  contains(member) {
    return this._ready.has(member);
  }

  toString() {
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
  constructor(strictOrder = true) {
    this.strictOrder = strictOrder;
    this._groups = new Map();
    this._memberIndex = new Map();
  }

  /** Admit members as one group. Returns the admitted group. */
  admit(groupId, members) {
    const group = new Group(groupId, members);
    if (this._groups.has(groupId)) {
      throw new TitoError(`group ${groupId} is already in the queue`);
    }
    const queued = group.members.filter((member) => this._memberIndex.has(member));
    if (queued.length > 0) {
      throw new TitoError(`members already in the queue: ${queued.join(' ')}`);
    }
    this._groups.set(groupId, group);
    for (const member of group.members) {
      this._memberIndex.set(member, groupId);
    }
    return group;
  }

  /** Mark a queued member ready. Returns true if its group is ready. */
  markReady(member) {
    const group = this.groupOf(member);
    if (group === null) {
      throw new TitoError(`${member} is not in the queue`);
    }
    return group.markReady(member);
  }

  /** Mark every member of a queued group ready. */
  markGroupReady(groupId) {
    const group = this._groups.get(groupId);
    if (group === undefined) {
      throw new TitoError(`group ${groupId} is not in the queue`);
    }
    for (const member of group.members) {
      group.markReady(member);
    }
    return true;
  }

  /** The group a queued member belongs to, or null if not queued. */
  groupOf(member) {
    const groupId = this._memberIndex.get(member);
    if (groupId === undefined) {
      return null;
    }
    return this._groups.get(groupId);
  }

  /** The next group that would be released, without releasing it. */
  peek() {
    for (const group of this._groups.values()) {
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
  release() {
    const group = this.peek();
    if (group === null) {
      return null;
    }
    this._remove(group);
    return group;
  }

  /** Release every group that can currently depart, in order. */
  releaseAll() {
    const released = [];
    for (;;) {
      const group = this.release();
      if (group === null) {
        return released;
      }
      released.push(group);
    }
  }

  /** Withdraw a waiting group, ready or not, and return it. */
  cancel(groupId) {
    const group = this._groups.get(groupId);
    if (group === undefined) {
      throw new TitoError(`group ${groupId} is not in the queue`);
    }
    this._remove(group);
    return group;
  }

  /** Withdraw every waiting group, in arrival order, and return them. */
  clear() {
    const cleared = [...this._groups.values()];
    this._groups.clear();
    this._memberIndex.clear();
    return cleared;
  }

  /** Waiting groups, in arrival order. */
  get groups() {
    return [...this._groups.values()];
  }

  get size() {
    return this._groups.size;
  }

  contains(member) {
    return this._memberIndex.has(member);
  }

  _remove(group) {
    this._groups.delete(group.groupId);
    for (const member of group.members) {
      this._memberIndex.delete(member);
    }
  }

  toString() {
    return `TitoQueue(strictOrder=${this.strictOrder}, groups=${this._groups.size})`;
  }
}

/** Format a boolean the same way in every example language. */
function flag(value) {
  return value ? 'true' : 'false';
}

/** Format an optional group, as returned by peek() and release(). */
function show(group) {
  return group === null ? 'waiting' : `${group}`;
}

/** Format the group lists returned by releaseAll() and clear(). */
function showAll(groups) {
  if (groups.length === 0) {
    return 'none';
  }
  return groups.map((group) => `${group}`).join(', ');
}

/** Format the group ids of the waiting groups. */
function showIds(groups) {
  if (groups.length === 0) {
    return 'none';
  }
  return groups.map((group) => group.groupId).join(' ');
}

/** Head-of-line FIFO: party-2 waits behind party-1 until it departs. */
function strictOrderDemo() {
  console.log('-- strict order --');
  const queue = new TitoQueue();
  console.log(`admit ${queue.admit('party-1', ['ann', 'bob'])}`);
  console.log(`admit ${queue.admit('party-2', ['cy'])}`);
  console.log(`len ${queue.size}, groups ${showIds(queue.groups)}`);
  console.log(`contains ann ${flag(queue.contains('ann'))}, contains zoe ${flag(queue.contains('zoe'))}`);

  const party1 = queue.groupOf('bob');
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
function relaxedOrderDemo() {
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
function cancelAndClearDemo() {
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
function attempt(label, action) {
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
function errorDemo() {
  console.log('-- errors --');
  const queue = new TitoQueue();
  console.log(`admit ${queue.admit('party-8', ['kim'])}`);

  attempt('admit party-8 [kim]', () => queue.admit('party-8', ['kim']));
  attempt('admit party-9 []', () => queue.admit('party-9', []));
  attempt('admit party-9 [jay jay]', () => queue.admit('party-9', ['jay', 'jay']));
  attempt('admit party-9 [kim]', () => queue.admit('party-9', ['kim']));
  attempt('mark_ready zoe', () => queue.markReady('zoe'));
  attempt('party-8.mark_ready zoe', () => queue.groupOf('kim').markReady('zoe'));
  attempt('mark_group_ready party-9', () => queue.markGroupReady('party-9'));
  attempt('cancel party-9', () => queue.cancel('party-9'));
}

function main() {
  strictOrderDemo();
  console.log('');
  relaxedOrderDemo();
  console.log('');
  cancelAndClearDemo();
  console.log('');
  errorDemo();
}

main();
