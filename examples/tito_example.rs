// Together In Together Out - Rust example.
//
// Run: rustc -O -o /tmp/tito_rust examples/tito_example.rs && /tmp/tito_rust

use std::collections::HashMap;
use std::fmt;

/// Raised when an operation would violate the TITO invariants.
#[derive(Debug)]
struct TitoError(String);

impl fmt::Display for TitoError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for TitoError {}

/// A set of members admitted together. It departs only once every member has
/// been marked ready.
struct Group {
    group_id: String,
    members: Vec<String>,
    ready: HashMap<String, bool>,
    ready_count: usize,
}

impl Group {
    fn new(group_id: &str, members: &[&str]) -> Result<Group, TitoError> {
        if members.is_empty() {
            return Err(TitoError(format!(
                "group {} must contain at least one member",
                group_id
            )));
        }
        let mut ready = HashMap::with_capacity(members.len());
        for member in members {
            if ready.insert((*member).to_string(), false).is_some() {
                return Err(TitoError(format!(
                    "group {} contains duplicate members",
                    group_id
                )));
            }
        }
        Ok(Group {
            group_id: group_id.to_string(),
            members: members.iter().map(|m| (*m).to_string()).collect(),
            ready,
            ready_count: 0,
        })
    }

    /// Members already marked ready, in admission order.
    fn ready_members(&self) -> Vec<&str> {
        self.members
            .iter()
            .filter(|m| self.ready[m.as_str()])
            .map(String::as_str)
            .collect()
    }

    /// Members not yet marked ready, in admission order.
    fn waiting_members(&self) -> Vec<&str> {
        self.members
            .iter()
            .filter(|m| !self.ready[m.as_str()])
            .map(String::as_str)
            .collect()
    }

    fn ready_count(&self) -> usize {
        self.ready_count
    }

    fn is_ready(&self) -> bool {
        self.ready_count == self.members.len()
    }

    /// Mark one member ready. Returns true once the whole group is ready.
    fn mark_ready(&mut self, member: &str) -> Result<bool, TitoError> {
        if !self.ready.contains_key(member) {
            return Err(TitoError(format!(
                "{} is not a member of group {}",
                member, self.group_id
            )));
        }
        if let Some(flag) = self.ready.get_mut(member) {
            if !*flag {
                *flag = true;
                self.ready_count += 1;
            }
        }
        Ok(self.is_ready())
    }

    fn len(&self) -> usize {
        self.members.len()
    }

    fn contains(&self, member: &str) -> bool {
        self.ready.contains_key(member)
    }
}

impl fmt::Display for Group {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} [{}]", self.group_id, self.members.join(" "))
    }
}

/// A queue that admits and releases members group by group.
///
/// `strict_order` true (the default policy) is head-of-line FIFO: only the
/// oldest waiting group may depart. `strict_order` false lets any fully ready
/// group depart, still oldest first, so a waiting group does not block the
/// ready groups behind it.
struct TitoQueue {
    strict_order: bool,
    groups: Vec<Group>,
    member_index: HashMap<String, String>,
}

impl TitoQueue {
    fn new(strict_order: bool) -> TitoQueue {
        TitoQueue {
            strict_order,
            groups: Vec::new(),
            member_index: HashMap::new(),
        }
    }

    fn strict_order(&self) -> bool {
        self.strict_order
    }

    /// Admit members as one group and return it.
    fn admit(&mut self, group_id: &str, members: &[&str]) -> Result<&Group, TitoError> {
        let group = Group::new(group_id, members)?;
        if self.groups.iter().any(|g| g.group_id == group_id) {
            return Err(TitoError(format!(
                "group {} is already in the queue",
                group_id
            )));
        }
        let queued: Vec<&str> = group
            .members
            .iter()
            .filter(|m| self.member_index.contains_key(m.as_str()))
            .map(String::as_str)
            .collect();
        if !queued.is_empty() {
            return Err(TitoError(format!(
                "members already in the queue: {}",
                queued.join(" ")
            )));
        }
        for member in &group.members {
            self.member_index
                .insert(member.clone(), group_id.to_string());
        }
        self.groups.push(group);
        Ok(self.groups.last().expect("group was just admitted"))
    }

    /// Mark a queued member ready. Returns true once its group is ready.
    fn mark_ready(&mut self, member: &str) -> Result<bool, TitoError> {
        match self.group_of_mut(member) {
            Some(group) => group.mark_ready(member),
            None => Err(TitoError(format!("{} is not in the queue", member))),
        }
    }

    /// Mark every member of a queued group ready.
    fn mark_group_ready(&mut self, group_id: &str) -> Result<bool, TitoError> {
        let group = match self.groups.iter_mut().find(|g| g.group_id == group_id) {
            Some(group) => group,
            None => {
                return Err(TitoError(format!(
                    "group {} is not in the queue",
                    group_id
                )))
            }
        };
        let members = group.members.clone();
        for member in &members {
            group.mark_ready(member)?;
        }
        Ok(true)
    }

    /// The group a queued member belongs to, or None if not queued.
    fn group_of(&self, member: &str) -> Option<&Group> {
        let group_id = self.member_index.get(member)?;
        self.groups.iter().find(|g| &g.group_id == group_id)
    }

    fn group_of_mut(&mut self, member: &str) -> Option<&mut Group> {
        let group_id = self.member_index.get(member)?.clone();
        self.groups.iter_mut().find(|g| g.group_id == group_id)
    }

    /// The next group that would be released, without releasing it.
    fn peek(&self) -> Option<&Group> {
        self.next_index().map(|index| &self.groups[index])
    }

    /// Release the next group that can depart, or None.
    fn release(&mut self) -> Option<Group> {
        let index = self.next_index()?;
        Some(self.remove_at(index))
    }

    /// Release every group that can currently depart, in order.
    fn release_all(&mut self) -> Vec<Group> {
        let mut released = Vec::new();
        while let Some(group) = self.release() {
            released.push(group);
        }
        released
    }

    /// Withdraw a waiting group, ready or not, and return it.
    fn cancel(&mut self, group_id: &str) -> Result<Group, TitoError> {
        match self.groups.iter().position(|g| g.group_id == group_id) {
            Some(index) => Ok(self.remove_at(index)),
            None => Err(TitoError(format!(
                "group {} is not in the queue",
                group_id
            ))),
        }
    }

    /// Withdraw every waiting group, in arrival order, and return them.
    fn clear(&mut self) -> Vec<Group> {
        self.member_index.clear();
        std::mem::take(&mut self.groups)
    }

    /// Waiting groups, in arrival order.
    fn groups(&self) -> &[Group] {
        &self.groups
    }

    fn len(&self) -> usize {
        self.groups.len()
    }

    fn contains(&self, member: &str) -> bool {
        self.member_index.contains_key(member)
    }

    // The index of the next group to depart: the head if ready under strict
    // order, otherwise the oldest ready group.
    fn next_index(&self) -> Option<usize> {
        for (index, group) in self.groups.iter().enumerate() {
            if group.is_ready() {
                return Some(index);
            }
            if self.strict_order {
                // Head of the line blocks every group behind it.
                return None;
            }
        }
        None
    }

    fn remove_at(&mut self, index: usize) -> Group {
        let group = self.groups.remove(index);
        for member in &group.members {
            self.member_index.remove(member);
        }
        group
    }
}

fn flag(value: bool) -> &'static str {
    if value {
        "true"
    } else {
        "false"
    }
}

/// Format an optional group, as returned by peek and release.
fn show(group: Option<&Group>) -> String {
    match group {
        Some(group) => group.to_string(),
        None => "waiting".to_string(),
    }
}

/// Format the group lists returned by release_all and clear.
fn show_all(groups: &[Group]) -> String {
    if groups.is_empty() {
        return "none".to_string();
    }
    groups
        .iter()
        .map(Group::to_string)
        .collect::<Vec<_>>()
        .join(", ")
}

/// Format the ids of the waiting groups.
fn show_ids(groups: &[Group]) -> String {
    if groups.is_empty() {
        return "none".to_string();
    }
    groups
        .iter()
        .map(|g| g.group_id.clone())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Format a group's readiness the same way in both status lines.
fn status(group: &Group) -> String {
    format!(
        "{}/{} ready [{}] waiting [{}] is_ready {}",
        group.ready_count(),
        group.len(),
        group.ready_members().join(" "),
        group.waiting_members().join(" "),
        flag(group.is_ready())
    )
}

/// Head-of-line FIFO: party-2 waits behind party-1 until it departs.
fn strict_order_demo() -> Result<(), TitoError> {
    println!("-- strict order --");
    let mut queue = TitoQueue::new(true);
    println!("admit {}", queue.admit("party-1", &["ann", "bob"])?);
    println!("admit {}", queue.admit("party-2", &["cy"])?);
    println!("len {}, groups {}", queue.len(), show_ids(queue.groups()));
    println!(
        "contains ann {}, contains zoe {}",
        flag(queue.contains("ann")),
        flag(queue.contains("zoe"))
    );

    let party1 = queue.group_of("bob").expect("party-1 is queued");
    println!("group_of bob -> {}", party1.group_id);
    println!(
        "party-1: size {}, contains ann {}, contains zoe {}",
        party1.len(),
        flag(party1.contains("ann")),
        flag(party1.contains("zoe"))
    );

    println!(
        "mark_ready ann -> group ready {}",
        flag(queue.mark_ready("ann")?)
    );
    println!(
        "party-1: {}",
        status(queue.group_of("bob").expect("party-1 is queued"))
    );
    println!("peek -> {}", show(queue.peek()));
    println!("release -> {}", show(queue.release().as_ref()));

    let ready = queue
        .group_of_mut("bob")
        .expect("party-1 is queued")
        .mark_ready("bob")?;
    println!("party-1.mark_ready bob -> group ready {}", flag(ready));
    println!(
        "party-1: {}",
        status(queue.group_of("bob").expect("party-1 is queued"))
    );
    println!("peek -> {}", show(queue.peek()));
    println!("release -> {}", show(queue.release().as_ref()));

    println!(
        "mark_group_ready party-2 -> {}",
        flag(queue.mark_group_ready("party-2")?)
    );
    println!("release_all -> {}", show_all(&queue.release_all()));
    println!("len {}", queue.len());
    Ok(())
}

/// Without strict order, ready party-4 leaves ahead of waiting party-3.
fn relaxed_order_demo() -> Result<(), TitoError> {
    println!("-- relaxed order --");
    let mut queue = TitoQueue::new(false);
    println!("strict_order {}", flag(queue.strict_order()));
    println!("admit {}", queue.admit("party-3", &["dee", "eli"])?);
    println!("admit {}", queue.admit("party-4", &["fay"])?);

    println!(
        "mark_group_ready party-4 -> {}",
        flag(queue.mark_group_ready("party-4")?)
    );
    println!("peek -> {}", show(queue.peek()));
    println!("release -> {}", show(queue.release().as_ref()));

    println!(
        "mark_ready dee -> group ready {}",
        flag(queue.mark_ready("dee")?)
    );
    println!("release -> {}", show(queue.release().as_ref()));
    println!(
        "mark_ready eli -> group ready {}",
        flag(queue.mark_ready("eli")?)
    );
    println!("release_all -> {}", show_all(&queue.release_all()));
    println!("len {}", queue.len());
    Ok(())
}

/// Cancelling is the only way a group leaves before it is fully ready.
fn cancel_and_clear_demo() -> Result<(), TitoError> {
    println!("-- cancel and clear --");
    let mut queue = TitoQueue::new(true);
    println!("admit {}", queue.admit("party-5", &["gil", "hal"])?);
    println!("admit {}", queue.admit("party-6", &["ivy"])?);
    println!("admit {}", queue.admit("party-7", &["jay"])?);

    println!(
        "mark_ready gil -> group ready {}",
        flag(queue.mark_ready("gil")?)
    );
    let cancelled = queue.cancel("party-5")?;
    println!(
        "cancel party-5 -> {} {}/{} ready",
        cancelled,
        cancelled.ready_count(),
        cancelled.len()
    );
    println!("groups {}", show_ids(queue.groups()));
    println!("clear -> {}", show_all(&queue.clear()));
    println!(
        "len {}, contains ivy {}",
        queue.len(),
        flag(queue.contains("ivy"))
    );
    Ok(())
}

/// Run an operation that must fail, and print the reported reason.
fn attempt(label: &str, result: Result<(), TitoError>) {
    match result {
        Ok(()) => println!("{} -> no error", label),
        Err(error) => println!("{} -> {}", label, error),
    }
}

/// Every operation that would break the TITO invariants is rejected.
fn error_demo() {
    println!("-- errors --");
    let mut queue = TitoQueue::new(true);
    match queue.admit("party-8", &["kim"]) {
        Ok(group) => println!("admit {}", group),
        Err(error) => println!("admit -> {}", error),
    }

    attempt(
        "admit party-8 [kim]",
        queue.admit("party-8", &["kim"]).map(|_| ()),
    );
    attempt("admit party-9 []", queue.admit("party-9", &[]).map(|_| ()));
    attempt(
        "admit party-9 [jay jay]",
        queue.admit("party-9", &["jay", "jay"]).map(|_| ()),
    );
    attempt(
        "admit party-9 [kim]",
        queue.admit("party-9", &["kim"]).map(|_| ()),
    );
    attempt("mark_ready zoe", queue.mark_ready("zoe").map(|_| ()));
    attempt(
        "party-8.mark_ready zoe",
        queue
            .group_of_mut("kim")
            .expect("kim is queued")
            .mark_ready("zoe")
            .map(|_| ()),
    );
    attempt(
        "mark_group_ready party-9",
        queue.mark_group_ready("party-9").map(|_| ()),
    );
    attempt("cancel party-9", queue.cancel("party-9").map(|_| ()));
}

fn main() -> Result<(), TitoError> {
    strict_order_demo()?;
    println!();
    relaxed_order_demo()?;
    println!();
    cancel_and_clear_demo()?;
    println!();
    error_demo();
    Ok(())
}
