// Together In Together Out - C++ example.
//
// Run: g++ -std=c++17 -O2 -o /tmp/tito_cpp examples/tito_example.cpp
//      && /tmp/tito_cpp

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

// Raised when an operation would violate the TITO invariants.
class TitoError : public std::runtime_error {
public:
    explicit TitoError(const std::string& message) : std::runtime_error(message) {}
};

// A set of members that entered the queue together. A group is only ever
// released as a whole: it departs once, and only once, every member is ready.
class Group {
public:
    Group(std::string group_id, std::vector<std::string> members)
        : group_id_(std::move(group_id)), members_(std::move(members)) {
        if (members_.empty()) {
            throw TitoError("group " + group_id_ + " must contain at least one member");
        }
        ready_.reserve(members_.size());
        for (const auto& member : members_) {
            // The ready map doubles as the membership set, so a repeated name
            // fails to insert and is reported as a duplicate.
            if (!ready_.emplace(member, false).second) {
                throw TitoError("group " + group_id_ + " contains duplicate members");
            }
        }
    }

    const std::string& group_id() const { return group_id_; }
    const std::vector<std::string>& members() const { return members_; }

    // Members already marked ready, in admission order.
    std::vector<std::string> ready_members() const { return filter(true); }

    // Members not yet marked ready, in admission order.
    std::vector<std::string> waiting_members() const { return filter(false); }

    std::size_t ready_count() const { return ready_count_; }
    bool is_ready() const { return ready_count_ == members_.size(); }

    // Mark one member ready. Returns true once the whole group is ready.
    bool mark_ready(const std::string& member) {
        auto it = ready_.find(member);
        if (it == ready_.end()) {
            throw TitoError(member + " is not a member of group " + group_id_);
        }
        if (!it->second) {
            it->second = true;
            ++ready_count_;
        }
        return is_ready();
    }

    std::size_t size() const { return members_.size(); }
    bool contains(const std::string& member) const { return ready_.count(member) != 0; }

    std::string str() const {
        std::string text = group_id_ + " [";
        for (std::size_t i = 0; i < members_.size(); ++i) {
            if (i != 0) {
                text += ' ';
            }
            text += members_[i];
        }
        text += ']';
        return text;
    }

private:
    std::vector<std::string> filter(bool ready) const {
        std::vector<std::string> out;
        for (const auto& member : members_) {
            if (ready_.at(member) == ready) {
                out.push_back(member);
            }
        }
        return out;
    }

    std::string group_id_;
    std::vector<std::string> members_;
    std::unordered_map<std::string, bool> ready_;
    std::size_t ready_count_ = 0;
};

// A queue that admits and releases members group by group.
//
// strict_order = true (the default) is head-of-line FIFO: only the oldest
// waiting group may depart. strict_order = false lets any fully ready group
// depart, still oldest first, so a waiting group does not block ready groups
// behind it.
class TitoQueue {
public:
    explicit TitoQueue(bool strict_order = true) : strict_order_(strict_order) {}

    bool strict_order() const { return strict_order_; }

    // Admit members as one group. Returns the admitted group.
    Group& admit(const std::string& group_id, const std::vector<std::string>& members) {
        auto group = std::make_unique<Group>(group_id, members);
        if (index_of(group_id) != npos) {
            throw TitoError("group " + group_id + " is already in the queue");
        }
        std::string queued;
        for (const auto& member : group->members()) {
            if (member_index_.count(member) != 0) {
                if (!queued.empty()) {
                    queued += ' ';
                }
                queued += member;
            }
        }
        if (!queued.empty()) {
            throw TitoError("members already in the queue: " + queued);
        }
        Group* raw = group.get();
        groups_.push_back(std::move(group));
        for (const auto& member : raw->members()) {
            member_index_[member] = group_id;
        }
        return *raw;
    }

    // Mark a queued member ready. Returns true if its group is ready.
    bool mark_ready(const std::string& member) {
        Group* group = group_of(member);
        if (group == nullptr) {
            throw TitoError(member + " is not in the queue");
        }
        return group->mark_ready(member);
    }

    // Mark every member of a queued group ready.
    bool mark_group_ready(const std::string& group_id) {
        Group* group = find(group_id);
        if (group == nullptr) {
            throw TitoError("group " + group_id + " is not in the queue");
        }
        for (const auto& member : group->members()) {
            group->mark_ready(member);
        }
        return true;
    }

    // The group a queued member belongs to, or nullptr if not queued.
    Group* group_of(const std::string& member) {
        auto it = member_index_.find(member);
        if (it == member_index_.end()) {
            return nullptr;
        }
        return find(it->second);
    }

    // The next group that would be released, without releasing it.
    Group* peek() {
        std::size_t index = peek_index();
        return index == npos ? nullptr : groups_[index].get();
    }

    // Release the next fully ready group, or nullptr if none can depart.
    std::unique_ptr<Group> release() {
        std::size_t index = peek_index();
        if (index == npos) {
            return nullptr;
        }
        return remove_at(index);
    }

    // Release every group that can currently depart, in order.
    std::vector<std::unique_ptr<Group>> release_all() {
        std::vector<std::unique_ptr<Group>> released;
        while (auto group = release()) {
            released.push_back(std::move(group));
        }
        return released;
    }

    // Withdraw a waiting group, ready or not, and return it.
    std::unique_ptr<Group> cancel(const std::string& group_id) {
        std::size_t index = index_of(group_id);
        if (index == npos) {
            throw TitoError("group " + group_id + " is not in the queue");
        }
        return remove_at(index);
    }

    // Withdraw every waiting group, in arrival order, and return them.
    std::vector<std::unique_ptr<Group>> clear() {
        std::vector<std::unique_ptr<Group>> cleared = std::move(groups_);
        groups_.clear();
        member_index_.clear();
        return cleared;
    }

    // Waiting groups, in arrival order.
    std::vector<const Group*> groups() const {
        std::vector<const Group*> out;
        for (const auto& group : groups_) {
            out.push_back(group.get());
        }
        return out;
    }

    std::size_t size() const { return groups_.size(); }
    bool contains(const std::string& member) const { return member_index_.count(member) != 0; }

private:
    static constexpr std::size_t npos = static_cast<std::size_t>(-1);

    std::size_t index_of(const std::string& group_id) const {
        for (std::size_t i = 0; i < groups_.size(); ++i) {
            if (groups_[i]->group_id() == group_id) {
                return i;
            }
        }
        return npos;
    }

    Group* find(const std::string& group_id) {
        std::size_t index = index_of(group_id);
        return index == npos ? nullptr : groups_[index].get();
    }

    std::size_t peek_index() const {
        if (groups_.empty()) {
            return npos;
        }
        if (strict_order_) {
            // The head of the line blocks every group behind it.
            return groups_.front()->is_ready() ? 0 : npos;
        }
        for (std::size_t i = 0; i < groups_.size(); ++i) {
            if (groups_[i]->is_ready()) {
                return i;
            }
        }
        return npos;
    }

    std::unique_ptr<Group> remove_at(std::size_t index) {
        std::unique_ptr<Group> group = std::move(groups_[index]);
        groups_.erase(groups_.begin() + static_cast<std::ptrdiff_t>(index));
        for (const auto& member : group->members()) {
            member_index_.erase(member);
        }
        return group;
    }

    bool strict_order_;
    // unique_ptr keeps each group at a stable address, so group_of() and peek()
    // can hand back raw pointers while release() and cancel() hand ownership on.
    std::vector<std::unique_ptr<Group>> groups_;
    std::unordered_map<std::string, std::string> member_index_;
};

std::string flag(bool value) { return value ? "true" : "false"; }

std::string join(const std::vector<std::string>& parts) {
    std::string joined;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i != 0) {
            joined += ' ';
        }
        joined += parts[i];
    }
    return joined;
}

// Format an optional group, as returned by peek() and release().
std::string show(const Group* group) { return group == nullptr ? "waiting" : group->str(); }

// Format the group lists returned by release_all() and clear().
std::string show_all(const std::vector<std::unique_ptr<Group>>& groups) {
    if (groups.empty()) {
        return "none";
    }
    std::string text;
    for (std::size_t i = 0; i < groups.size(); ++i) {
        if (i != 0) {
            text += ", ";
        }
        text += groups[i]->str();
    }
    return text;
}

// Format the group ids of the waiting groups.
std::string show_ids(const std::vector<const Group*>& groups) {
    if (groups.empty()) {
        return "none";
    }
    std::string text;
    for (std::size_t i = 0; i < groups.size(); ++i) {
        if (i != 0) {
            text += ' ';
        }
        text += groups[i]->group_id();
    }
    return text;
}

void print_state(const Group& group) {
    std::cout << group.group_id() << ": " << group.ready_count() << "/" << group.size()
              << " ready [" << join(group.ready_members()) << "] waiting ["
              << join(group.waiting_members()) << "] is_ready " << flag(group.is_ready()) << "\n";
}

// Head-of-line FIFO: party-2 waits behind party-1 until it departs.
void strict_order_demo() {
    std::cout << "-- strict order --\n";
    TitoQueue queue;
    std::cout << "admit " << queue.admit("party-1", {"ann", "bob"}).str() << "\n";
    std::cout << "admit " << queue.admit("party-2", {"cy"}).str() << "\n";
    std::cout << "len " << queue.size() << ", groups " << show_ids(queue.groups()) << "\n";
    std::cout << "contains ann " << flag(queue.contains("ann")) << ", contains zoe "
              << flag(queue.contains("zoe")) << "\n";

    Group* party1 = queue.group_of("bob");
    std::cout << "group_of bob -> " << party1->group_id() << "\n";
    std::cout << "party-1: size " << party1->size() << ", contains ann "
              << flag(party1->contains("ann")) << ", contains zoe "
              << flag(party1->contains("zoe")) << "\n";

    std::cout << "mark_ready ann -> group ready " << flag(queue.mark_ready("ann")) << "\n";
    print_state(*party1);
    std::cout << "peek -> " << show(queue.peek()) << "\n";
    std::cout << "release -> " << show(queue.release().get()) << "\n";

    std::cout << "party-1.mark_ready bob -> group ready " << flag(party1->mark_ready("bob")) << "\n";
    print_state(*party1);
    std::cout << "peek -> " << show(queue.peek()) << "\n";
    std::cout << "release -> " << show(queue.release().get()) << "\n";

    std::cout << "mark_group_ready party-2 -> " << flag(queue.mark_group_ready("party-2")) << "\n";
    std::cout << "release_all -> " << show_all(queue.release_all()) << "\n";
    std::cout << "len " << queue.size() << "\n";
}

// Without strict order, ready party-4 leaves ahead of waiting party-3.
void relaxed_order_demo() {
    std::cout << "-- relaxed order --\n";
    TitoQueue queue(false);
    std::cout << "strict_order " << flag(queue.strict_order()) << "\n";
    std::cout << "admit " << queue.admit("party-3", {"dee", "eli"}).str() << "\n";
    std::cout << "admit " << queue.admit("party-4", {"fay"}).str() << "\n";

    std::cout << "mark_group_ready party-4 -> " << flag(queue.mark_group_ready("party-4")) << "\n";
    std::cout << "peek -> " << show(queue.peek()) << "\n";
    std::cout << "release -> " << show(queue.release().get()) << "\n";

    std::cout << "mark_ready dee -> group ready " << flag(queue.mark_ready("dee")) << "\n";
    std::cout << "release -> " << show(queue.release().get()) << "\n";
    std::cout << "mark_ready eli -> group ready " << flag(queue.mark_ready("eli")) << "\n";
    std::cout << "release_all -> " << show_all(queue.release_all()) << "\n";
    std::cout << "len " << queue.size() << "\n";
}

// Cancelling is the only way a group leaves before it is fully ready.
void cancel_and_clear_demo() {
    std::cout << "-- cancel and clear --\n";
    TitoQueue queue;
    std::cout << "admit " << queue.admit("party-5", {"gil", "hal"}).str() << "\n";
    std::cout << "admit " << queue.admit("party-6", {"ivy"}).str() << "\n";
    std::cout << "admit " << queue.admit("party-7", {"jay"}).str() << "\n";

    std::cout << "mark_ready gil -> group ready " << flag(queue.mark_ready("gil")) << "\n";
    auto cancelled = queue.cancel("party-5");
    std::cout << "cancel party-5 -> " << cancelled->str() << " " << cancelled->ready_count()
              << "/" << cancelled->size() << " ready\n";
    std::cout << "groups " << show_ids(queue.groups()) << "\n";
    std::cout << "clear -> " << show_all(queue.clear()) << "\n";
    std::cout << "len " << queue.size() << ", contains ivy " << flag(queue.contains("ivy")) << "\n";
}

// Run an operation that must fail, and print the reported reason.
template <typename Action>
void attempt(const std::string& label, Action action) {
    try {
        action();
        std::cout << label << " -> no error\n";
    } catch (const TitoError& error) {
        std::cout << label << " -> " << error.what() << "\n";
    }
}

// Every operation that would break the TITO invariants is rejected.
void error_demo() {
    std::cout << "-- errors --\n";
    TitoQueue queue;
    std::cout << "admit " << queue.admit("party-8", {"kim"}).str() << "\n";

    attempt("admit party-8 [kim]", [&] { queue.admit("party-8", {"kim"}); });
    attempt("admit party-9 []", [&] { queue.admit("party-9", {}); });
    attempt("admit party-9 [jay jay]", [&] { queue.admit("party-9", {"jay", "jay"}); });
    attempt("admit party-9 [kim]", [&] { queue.admit("party-9", {"kim"}); });
    attempt("mark_ready zoe", [&] { queue.mark_ready("zoe"); });
    attempt("party-8.mark_ready zoe", [&] { queue.group_of("kim")->mark_ready("zoe"); });
    attempt("mark_group_ready party-9", [&] { queue.mark_group_ready("party-9"); });
    attempt("cancel party-9", [&] { queue.cancel("party-9"); });
}

}  // namespace

int main() {
    strict_order_demo();
    std::cout << "\n";
    relaxed_order_demo();
    std::cout << "\n";
    cancel_and_clear_demo();
    std::cout << "\n";
    error_demo();
    return 0;
}
