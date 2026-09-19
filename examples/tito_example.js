// Together In Together Out - JavaScript example.
//
// Run: node examples/tito_example.js

'use strict';

/** Minimal strict-order (head-of-line FIFO) TITO queue. */
class TitoQueue {
  constructor() {
    this.order = [];
    this.groups = new Map();
    this.groupOf = new Map();
  }

  admit(groupId, members) {
    if (members.length === 0) {
      throw new Error('a group must contain at least one member');
    }
    if (this.groups.has(groupId)) {
      throw new Error(`duplicate group id: ${groupId}`);
    }
    const ready = new Map();
    for (const member of members) {
      if (this.groupOf.has(member) || ready.has(member)) {
        throw new Error(`duplicate member: ${member}`);
      }
      ready.set(member, false);
    }
    for (const member of members) {
      this.groupOf.set(member, groupId);
    }
    this.groups.set(groupId, ready);
    this.order.push(groupId);
  }

  markReady(member) {
    const groupId = this.groupOf.get(member);
    if (groupId === undefined) {
      throw new Error(`unknown member: ${member}`);
    }
    this.groups.get(groupId).set(member, true);
  }

  /** Release the head group, or null while it is not fully ready. */
  release() {
    if (this.order.length === 0) {
      return null;
    }
    const groupId = this.order[0];
    const ready = this.groups.get(groupId);
    for (const isReady of ready.values()) {
      if (!isReady) {
        return null;
      }
    }
    this.order.shift();
    this.groups.delete(groupId);
    const members = [...ready.keys()];
    for (const member of members) {
      this.groupOf.delete(member);
    }
    return { groupId, members };
  }
}

function main() {
  const queue = new TitoQueue();

  queue.admit('party-1', ['ann', 'bob']);
  console.log('admit party-1: ann, bob');
  queue.admit('party-2', ['cy']);
  console.log('admit party-2: cy');

  for (const member of ['ann', 'bob', 'cy']) {
    queue.markReady(member);
    console.log(`ready ${member}`);
    const released = queue.release();
    if (released === null) {
      console.log('release -> waiting');
    } else {
      console.log(`release -> ${released.groupId} [${released.members.join(' ')}]`);
    }
  }
}

main();
