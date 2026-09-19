// Together In Together Out - Rust example.
//
// Run: rustc -O -o /tmp/tito_rust examples/tito_example.rs && /tmp/tito_rust

use std::collections::{HashSet, VecDeque};

struct Group {
    id: String,
    members: Vec<String>,
    ready: HashSet<String>,
}

/// Minimal strict-order (head-of-line FIFO) TITO queue.
struct TitoQueue {
    order: VecDeque<Group>,
    ids: HashSet<String>,
    queued_members: HashSet<String>,
}

impl TitoQueue {
    fn new() -> Self {
        TitoQueue {
            order: VecDeque::new(),
            ids: HashSet::new(),
            queued_members: HashSet::new(),
        }
    }

    fn admit(&mut self, id: &str, members: &[&str]) -> Result<(), String> {
        if members.is_empty() {
            return Err("a group must contain at least one member".to_string());
        }
        if self.ids.contains(id) {
            return Err(format!("duplicate group id: {}", id));
        }
        let mut seen = HashSet::new();
        for member in members {
            if self.queued_members.contains(*member) || !seen.insert(member.to_string()) {
                return Err(format!("duplicate member: {}", member));
            }
        }
        for member in members {
            self.queued_members.insert(member.to_string());
        }
        self.ids.insert(id.to_string());
        self.order.push_back(Group {
            id: id.to_string(),
            members: members.iter().map(|m| m.to_string()).collect(),
            ready: HashSet::new(),
        });
        Ok(())
    }

    fn mark_ready(&mut self, member: &str) -> Result<(), String> {
        let group = self
            .order
            .iter_mut()
            .find(|g| g.members.iter().any(|m| m == member))
            .ok_or_else(|| format!("unknown member: {}", member))?;
        group.ready.insert(member.to_string());
        Ok(())
    }

    /// Release the head group, or `None` while it is not fully ready.
    fn release(&mut self) -> Option<Group> {
        let head = self.order.front()?;
        if head.ready.len() != head.members.len() {
            return None;
        }
        let group = self.order.pop_front()?;
        self.ids.remove(&group.id);
        for member in &group.members {
            self.queued_members.remove(member);
        }
        Some(group)
    }
}

fn main() {
    let mut queue = TitoQueue::new();

    queue.admit("party-1", &["ann", "bob"]).unwrap();
    println!("admit party-1: ann, bob");
    queue.admit("party-2", &["cy"]).unwrap();
    println!("admit party-2: cy");

    for member in ["ann", "bob", "cy"] {
        queue.mark_ready(member).unwrap();
        println!("ready {}", member);
        match queue.release() {
            None => println!("release -> waiting"),
            Some(group) => println!("release -> {} [{}]", group.id, group.members.join(" ")),
        }
    }
}
