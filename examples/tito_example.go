// Together In Together Out - Go example.
//
// Run: go run examples/tito_example.go

package main

import (
	"fmt"
	"strings"
)

// group is a set of members admitted together. It departs only once every
// member has been marked ready.
type group struct {
	groupID    string
	members    []string
	ready      map[string]bool
	readyCount int
}

// newGroup validates the members and returns the group they form.
func newGroup(groupID string, members []string) (*group, error) {
	if len(members) == 0 {
		return nil, fmt.Errorf("group %s must contain at least one member", groupID)
	}
	ready := make(map[string]bool, len(members))
	for _, member := range members {
		if _, dup := ready[member]; dup {
			return nil, fmt.Errorf("group %s contains duplicate members", groupID)
		}
		ready[member] = false
	}
	return &group{
		groupID: groupID,
		members: append([]string(nil), members...),
		ready:   ready,
	}, nil
}

// readyMembers lists the members already marked ready, in admission order.
func (g *group) readyMembers() []string {
	members := make([]string, 0, g.readyCount)
	for _, member := range g.members {
		if g.ready[member] {
			members = append(members, member)
		}
	}
	return members
}

// waitingMembers lists the members not yet marked ready, in admission order.
func (g *group) waitingMembers() []string {
	members := make([]string, 0, len(g.members)-g.readyCount)
	for _, member := range g.members {
		if !g.ready[member] {
			members = append(members, member)
		}
	}
	return members
}

func (g *group) isReady() bool {
	return g.readyCount == len(g.members)
}

// markReady marks one member ready and reports whether the whole group is.
func (g *group) markReady(member string) (bool, error) {
	ready, ok := g.ready[member]
	if !ok {
		return false, fmt.Errorf("%s is not a member of group %s", member, g.groupID)
	}
	if !ready {
		g.ready[member] = true
		g.readyCount++
	}
	return g.isReady(), nil
}

func (g *group) size() int {
	return len(g.members)
}

func (g *group) contains(member string) bool {
	_, ok := g.ready[member]
	return ok
}

func (g *group) String() string {
	return fmt.Sprintf("%s [%s]", g.groupID, strings.Join(g.members, " "))
}

// titoQueue admits and releases members group by group.
//
// strictOrder true (the default policy) is head-of-line FIFO: only the oldest
// waiting group may depart. strictOrder false lets any fully ready group
// depart, still oldest first, so a waiting group does not block the ready
// groups behind it.
type titoQueue struct {
	strictOrder bool
	order       []*group
	byID        map[string]*group
	memberIndex map[string]string
}

func newTitoQueue(strictOrder bool) *titoQueue {
	return &titoQueue{
		strictOrder: strictOrder,
		byID:        make(map[string]*group),
		memberIndex: make(map[string]string),
	}
}

// admit adds members as one group and returns it.
func (q *titoQueue) admit(groupID string, members []string) (*group, error) {
	g, err := newGroup(groupID, members)
	if err != nil {
		return nil, err
	}
	if _, exists := q.byID[groupID]; exists {
		return nil, fmt.Errorf("group %s is already in the queue", groupID)
	}
	var queued []string
	for _, member := range g.members {
		if _, taken := q.memberIndex[member]; taken {
			queued = append(queued, member)
		}
	}
	if len(queued) > 0 {
		return nil, fmt.Errorf("members already in the queue: %s", strings.Join(queued, " "))
	}
	q.order = append(q.order, g)
	q.byID[groupID] = g
	for _, member := range g.members {
		q.memberIndex[member] = groupID
	}
	return g, nil
}

// markReady marks a queued member ready and reports whether its group is.
func (q *titoQueue) markReady(member string) (bool, error) {
	g := q.groupOf(member)
	if g == nil {
		return false, fmt.Errorf("%s is not in the queue", member)
	}
	return g.markReady(member)
}

// markGroupReady marks every member of a queued group ready.
func (q *titoQueue) markGroupReady(groupID string) (bool, error) {
	g, ok := q.byID[groupID]
	if !ok {
		return false, fmt.Errorf("group %s is not in the queue", groupID)
	}
	for _, member := range g.members {
		if _, err := g.markReady(member); err != nil {
			return false, err
		}
	}
	return true, nil
}

// groupOf returns the group a queued member belongs to, or nil.
func (q *titoQueue) groupOf(member string) *group {
	groupID, ok := q.memberIndex[member]
	if !ok {
		return nil
	}
	return q.byID[groupID]
}

// peek returns the next group that would be released, without releasing it.
func (q *titoQueue) peek() *group {
	for _, g := range q.order {
		if g.isReady() {
			return g
		}
		if q.strictOrder {
			// Head of the line blocks every group behind it.
			return nil
		}
	}
	return nil
}

// release removes and returns the next group that can depart, or nil.
func (q *titoQueue) release() *group {
	g := q.peek()
	if g == nil {
		return nil
	}
	q.remove(g)
	return g
}

// releaseAll releases every group that can currently depart, in order.
func (q *titoQueue) releaseAll() []*group {
	var released []*group
	for {
		g := q.release()
		if g == nil {
			return released
		}
		released = append(released, g)
	}
}

// cancel withdraws a waiting group, ready or not, and returns it.
func (q *titoQueue) cancel(groupID string) (*group, error) {
	g, ok := q.byID[groupID]
	if !ok {
		return nil, fmt.Errorf("group %s is not in the queue", groupID)
	}
	q.remove(g)
	return g, nil
}

// clear withdraws every waiting group, in arrival order, and returns them.
func (q *titoQueue) clear() []*group {
	cleared := q.order
	q.order = nil
	q.byID = make(map[string]*group)
	q.memberIndex = make(map[string]string)
	return cleared
}

// groups returns the waiting groups, in arrival order.
func (q *titoQueue) groups() []*group {
	return q.order
}

func (q *titoQueue) count() int {
	return len(q.order)
}

func (q *titoQueue) contains(member string) bool {
	_, ok := q.memberIndex[member]
	return ok
}

// remove drops a group from the ordering and both member indexes.
func (q *titoQueue) remove(g *group) {
	for i, other := range q.order {
		if other == g {
			q.order = append(q.order[:i], q.order[i+1:]...)
			break
		}
	}
	delete(q.byID, g.groupID)
	for _, member := range g.members {
		delete(q.memberIndex, member)
	}
}

// must panics on an admission or cancellation the demo assumes succeeds.
func must(g *group, err error) *group {
	if err != nil {
		panic(err)
	}
	return g
}

// mustBool panics on a mark the demo assumes succeeds.
func mustBool(value bool, err error) bool {
	if err != nil {
		panic(err)
	}
	return value
}

func flag(value bool) string {
	if value {
		return "true"
	}
	return "false"
}

// show formats an optional group, as returned by peek and release.
func show(g *group) string {
	if g == nil {
		return "waiting"
	}
	return g.String()
}

// showAll formats the group lists returned by releaseAll and clear.
func showAll(groups []*group) string {
	if len(groups) == 0 {
		return "none"
	}
	parts := make([]string, len(groups))
	for i, g := range groups {
		parts[i] = g.String()
	}
	return strings.Join(parts, ", ")
}

// showIDs formats the ids of the waiting groups.
func showIDs(groups []*group) string {
	if len(groups) == 0 {
		return "none"
	}
	ids := make([]string, len(groups))
	for i, g := range groups {
		ids[i] = g.groupID
	}
	return strings.Join(ids, " ")
}

// strictOrderDemo shows head-of-line FIFO: party-2 waits behind party-1.
func strictOrderDemo() {
	fmt.Println("-- strict order --")
	queue := newTitoQueue(true)
	fmt.Printf("admit %s\n", must(queue.admit("party-1", []string{"ann", "bob"})))
	fmt.Printf("admit %s\n", must(queue.admit("party-2", []string{"cy"})))
	fmt.Printf("len %d, groups %s\n", queue.count(), showIDs(queue.groups()))
	fmt.Printf("contains ann %s, contains zoe %s\n", flag(queue.contains("ann")), flag(queue.contains("zoe")))

	party1 := queue.groupOf("bob")
	fmt.Printf("group_of bob -> %s\n", party1.groupID)
	fmt.Printf("party-1: size %d, contains ann %s, contains zoe %s\n",
		party1.size(), flag(party1.contains("ann")), flag(party1.contains("zoe")))

	fmt.Printf("mark_ready ann -> group ready %s\n", flag(mustBool(queue.markReady("ann"))))
	fmt.Printf("party-1: %d/%d ready [%s] waiting [%s] is_ready %s\n",
		party1.readyCount, party1.size(), strings.Join(party1.readyMembers(), " "),
		strings.Join(party1.waitingMembers(), " "), flag(party1.isReady()))
	fmt.Printf("peek -> %s\n", show(queue.peek()))
	fmt.Printf("release -> %s\n", show(queue.release()))

	fmt.Printf("party-1.mark_ready bob -> group ready %s\n", flag(mustBool(party1.markReady("bob"))))
	fmt.Printf("party-1: %d/%d ready [%s] waiting [%s] is_ready %s\n",
		party1.readyCount, party1.size(), strings.Join(party1.readyMembers(), " "),
		strings.Join(party1.waitingMembers(), " "), flag(party1.isReady()))
	fmt.Printf("peek -> %s\n", show(queue.peek()))
	fmt.Printf("release -> %s\n", show(queue.release()))

	fmt.Printf("mark_group_ready party-2 -> %s\n", flag(mustBool(queue.markGroupReady("party-2"))))
	fmt.Printf("release_all -> %s\n", showAll(queue.releaseAll()))
	fmt.Printf("len %d\n", queue.count())
}

// relaxedOrderDemo shows a ready party-4 leaving ahead of waiting party-3.
func relaxedOrderDemo() {
	fmt.Println("-- relaxed order --")
	queue := newTitoQueue(false)
	fmt.Printf("strict_order %s\n", flag(queue.strictOrder))
	fmt.Printf("admit %s\n", must(queue.admit("party-3", []string{"dee", "eli"})))
	fmt.Printf("admit %s\n", must(queue.admit("party-4", []string{"fay"})))

	fmt.Printf("mark_group_ready party-4 -> %s\n", flag(mustBool(queue.markGroupReady("party-4"))))
	fmt.Printf("peek -> %s\n", show(queue.peek()))
	fmt.Printf("release -> %s\n", show(queue.release()))

	fmt.Printf("mark_ready dee -> group ready %s\n", flag(mustBool(queue.markReady("dee"))))
	fmt.Printf("release -> %s\n", show(queue.release()))
	fmt.Printf("mark_ready eli -> group ready %s\n", flag(mustBool(queue.markReady("eli"))))
	fmt.Printf("release_all -> %s\n", showAll(queue.releaseAll()))
	fmt.Printf("len %d\n", queue.count())
}

// cancelAndClearDemo shows the only way a group leaves before it is ready.
func cancelAndClearDemo() {
	fmt.Println("-- cancel and clear --")
	queue := newTitoQueue(true)
	fmt.Printf("admit %s\n", must(queue.admit("party-5", []string{"gil", "hal"})))
	fmt.Printf("admit %s\n", must(queue.admit("party-6", []string{"ivy"})))
	fmt.Printf("admit %s\n", must(queue.admit("party-7", []string{"jay"})))

	fmt.Printf("mark_ready gil -> group ready %s\n", flag(mustBool(queue.markReady("gil"))))
	cancelled := must(queue.cancel("party-5"))
	fmt.Printf("cancel party-5 -> %s %d/%d ready\n", cancelled, cancelled.readyCount, cancelled.size())
	fmt.Printf("groups %s\n", showIDs(queue.groups()))
	fmt.Printf("clear -> %s\n", showAll(queue.clear()))
	fmt.Printf("len %d, contains ivy %s\n", queue.count(), flag(queue.contains("ivy")))
}

// attempt runs an operation that must fail, and prints the reported reason.
func attempt(label string, action func() error) {
	if err := action(); err != nil {
		fmt.Printf("%s -> %s\n", label, err)
	} else {
		fmt.Printf("%s -> no error\n", label)
	}
}

// errorDemo shows every operation that would break the invariants is rejected.
func errorDemo() {
	fmt.Println("-- errors --")
	queue := newTitoQueue(true)
	fmt.Printf("admit %s\n", must(queue.admit("party-8", []string{"kim"})))

	attempt("admit party-8 [kim]", func() error { _, err := queue.admit("party-8", []string{"kim"}); return err })
	attempt("admit party-9 []", func() error { _, err := queue.admit("party-9", []string{}); return err })
	attempt("admit party-9 [jay jay]", func() error { _, err := queue.admit("party-9", []string{"jay", "jay"}); return err })
	attempt("admit party-9 [kim]", func() error { _, err := queue.admit("party-9", []string{"kim"}); return err })
	attempt("mark_ready zoe", func() error { _, err := queue.markReady("zoe"); return err })
	attempt("party-8.mark_ready zoe", func() error { _, err := queue.groupOf("kim").markReady("zoe"); return err })
	attempt("mark_group_ready party-9", func() error { _, err := queue.markGroupReady("party-9"); return err })
	attempt("cancel party-9", func() error { _, err := queue.cancel("party-9"); return err })
}

func main() {
	strictOrderDemo()
	fmt.Println()
	relaxedOrderDemo()
	fmt.Println()
	cancelAndClearDemo()
	fmt.Println()
	errorDemo()
}
