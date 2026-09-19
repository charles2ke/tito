// Together In Together Out - Go example.
//
// Run: go run examples/tito_example.go

package main

import (
	"fmt"
	"strings"
)

type group struct {
	id      string
	members []string
	ready   map[string]bool
}

// titoQueue is a minimal strict-order (head-of-line FIFO) TITO queue.
type titoQueue struct {
	order   []*group
	ids     map[string]bool
	groupOf map[string]*group
}

func newTitoQueue() *titoQueue {
	return &titoQueue{
		ids:     make(map[string]bool),
		groupOf: make(map[string]*group),
	}
}

func (q *titoQueue) admit(id string, members []string) error {
	if len(members) == 0 {
		return fmt.Errorf("a group must contain at least one member")
	}
	if q.ids[id] {
		return fmt.Errorf("duplicate group id: %s", id)
	}
	g := &group{id: id, members: append([]string(nil), members...), ready: make(map[string]bool)}
	for _, member := range members {
		if _, taken := q.groupOf[member]; taken {
			return fmt.Errorf("duplicate member: %s", member)
		}
		if _, seen := g.ready[member]; seen {
			return fmt.Errorf("duplicate member: %s", member)
		}
		g.ready[member] = false
	}
	for _, member := range members {
		q.groupOf[member] = g
	}
	q.ids[id] = true
	q.order = append(q.order, g)
	return nil
}

func (q *titoQueue) markReady(member string) error {
	g, ok := q.groupOf[member]
	if !ok {
		return fmt.Errorf("unknown member: %s", member)
	}
	g.ready[member] = true
	return nil
}

// release returns the head group, or nil while it is not fully ready.
func (q *titoQueue) release() *group {
	if len(q.order) == 0 {
		return nil
	}
	g := q.order[0]
	for _, member := range g.members {
		if !g.ready[member] {
			return nil
		}
	}
	q.order = q.order[1:]
	delete(q.ids, g.id)
	for _, member := range g.members {
		delete(q.groupOf, member)
	}
	return g
}

func main() {
	queue := newTitoQueue()

	if err := queue.admit("party-1", []string{"ann", "bob"}); err != nil {
		panic(err)
	}
	fmt.Println("admit party-1: ann, bob")
	if err := queue.admit("party-2", []string{"cy"}); err != nil {
		panic(err)
	}
	fmt.Println("admit party-2: cy")

	for _, member := range []string{"ann", "bob", "cy"} {
		if err := queue.markReady(member); err != nil {
			panic(err)
		}
		fmt.Printf("ready %s\n", member)
		if released := queue.release(); released == nil {
			fmt.Println("release -> waiting")
		} else {
			fmt.Printf("release -> %s [%s]\n", released.id, strings.Join(released.members, " "))
		}
	}
}
