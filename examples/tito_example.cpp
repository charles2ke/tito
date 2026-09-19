// Together In Together Out - C++ example.
//
// Run: g++ -std=c++17 -O2 -o /tmp/tito_cpp examples/tito_example.cpp
//      && /tmp/tito_cpp

#include <deque>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

struct Group {
    std::string id;
    std::vector<std::string> members;
    std::unordered_set<std::string> ready;
};

// Minimal strict-order (head-of-line FIFO) TITO queue.
class TitoQueue {
public:
    void admit(const std::string& id, const std::vector<std::string>& members) {
        if (members.empty()) {
            throw std::invalid_argument("a group must contain at least one member");
        }
        if (ids_.count(id) != 0) {
            throw std::invalid_argument("duplicate group id: " + id);
        }
        for (const auto& member : members) {
            if (group_of_.count(member) != 0) {
                throw std::invalid_argument("duplicate member: " + member);
            }
        }
        order_.push_back(Group{id, members, {}});
        Group* group = &order_.back();
        for (const auto& member : members) {
            if (!group_of_.emplace(member, group).second) {
                throw std::invalid_argument("duplicate member: " + member);
            }
        }
        ids_.insert(id);
    }

    void mark_ready(const std::string& member) {
        auto it = group_of_.find(member);
        if (it == group_of_.end()) {
            throw std::invalid_argument("unknown member: " + member);
        }
        it->second->ready.insert(member);
    }

    // Release the head group into *out*; returns false while it is not ready.
    bool release(Group& out) {
        if (order_.empty()) {
            return false;
        }
        Group& head = order_.front();
        if (head.ready.size() != head.members.size()) {
            return false;
        }
        out = std::move(head);
        order_.pop_front();
        ids_.erase(out.id);
        for (const auto& member : out.members) {
            group_of_.erase(member);
        }
        return true;
    }

private:
    // A deque keeps element addresses stable across pushes at the back, so
    // group_of_ can point straight at the owning group.
    std::deque<Group> order_;
    std::unordered_set<std::string> ids_;
    std::unordered_map<std::string, Group*> group_of_;
};

std::string join(const std::vector<std::string>& parts) {
    std::string joined;
    for (const auto& part : parts) {
        if (!joined.empty()) {
            joined += ' ';
        }
        joined += part;
    }
    return joined;
}

}  // namespace

int main() {
    TitoQueue queue;

    queue.admit("party-1", {"ann", "bob"});
    std::cout << "admit party-1: ann, bob\n";
    queue.admit("party-2", {"cy"});
    std::cout << "admit party-2: cy\n";

    for (const std::string member : {"ann", "bob", "cy"}) {
        queue.mark_ready(member);
        std::cout << "ready " << member << "\n";
        Group released;
        if (!queue.release(released)) {
            std::cout << "release -> waiting\n";
        } else {
            std::cout << "release -> " << released.id << " [" << join(released.members) << "]\n";
        }
    }
    return 0;
}
