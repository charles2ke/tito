# Together In Together Out - Ruby example.
#
# Run: ruby examples/tito_example.rb

# Raised when an operation would violate the TITO invariants.
class TitoError < StandardError; end

# A set of members that entered the queue together.
#
# A group is only ever released as a whole: it departs when, and only
# when, all of its members have been marked ready.
class Group
  attr_reader :group_id, :members, :ready_count

  def initialize(group_id, members)
    members = members.to_a
    raise TitoError, "group #{group_id} must contain at least one member" if members.empty?

    # Keyed by member so membership is O(1) and the ready flag rides along;
    # insertion order is the admission order the demo prints.
    ready = {}
    members.each { |member| ready[member] = false }
    raise TitoError, "group #{group_id} contains duplicate members" if ready.size != members.size

    @group_id = group_id
    @members = members
    @ready = ready
    @ready_count = 0
  end

  # Members already marked ready, in admission order.
  def ready_members
    @members.select { |member| @ready[member] }
  end

  # Members not yet marked ready, in admission order.
  def waiting_members
    @members.reject { |member| @ready[member] }
  end

  # True once every member of the group is ready to depart.
  def ready?
    @ready_count == @members.size
  end

  # Mark one member ready. Returns true if the whole group is ready.
  def mark_ready(member)
    raise TitoError, "#{member} is not a member of group #{@group_id}" unless @ready.key?(member)

    unless @ready[member]
      @ready[member] = true
      @ready_count += 1
    end
    ready?
  end

  def size
    @members.size
  end

  def contains?(member)
    @ready.key?(member)
  end

  def to_s
    "#{@group_id} [#{@members.join(' ')}]"
  end
end

# A queue that admits and releases members group by group.
#
# strict_order: true (the default) is head-of-line FIFO: only the oldest
# waiting group may depart. strict_order: false lets any fully ready group
# depart, still oldest first, so a waiting group does not block the ready
# groups behind it.
class TitoQueue
  attr_reader :strict_order

  def initialize(strict_order: true)
    @strict_order = strict_order
    @groups = {}
    @member_index = {}
  end

  # Admit members as one group. Returns the admitted group.
  def admit(group_id, members)
    group = Group.new(group_id, members)
    raise TitoError, "group #{group_id} is already in the queue" if @groups.key?(group_id)

    queued = group.members.select { |member| @member_index.key?(member) }
    raise TitoError, "members already in the queue: #{queued.join(' ')}" unless queued.empty?

    @groups[group_id] = group
    group.members.each { |member| @member_index[member] = group_id }
    group
  end

  # Mark a queued member ready. Returns true if its group is ready.
  def mark_ready(member)
    group = group_of(member)
    raise TitoError, "#{member} is not in the queue" if group.nil?

    group.mark_ready(member)
  end

  # Mark every member of a queued group ready.
  def mark_group_ready(group_id)
    group = @groups[group_id]
    raise TitoError, "group #{group_id} is not in the queue" if group.nil?

    group.members.each { |member| group.mark_ready(member) }
    true
  end

  # The group a queued member belongs to, or nil if not queued.
  def group_of(member)
    group_id = @member_index[member]
    return nil if group_id.nil?

    @groups[group_id]
  end

  # The next group that would be released, without releasing it.
  def peek
    @groups.each_value do |group|
      return group if group.ready?
      return nil if @strict_order # Head of the line blocks every group behind it.
    end
    nil
  end

  # Release the next fully ready group, or nil if none can depart.
  def release
    group = peek
    return nil if group.nil?

    remove(group)
    group
  end

  # Release every group that can currently depart, in order.
  def release_all
    released = []
    while (group = release)
      released << group
    end
    released
  end

  # Withdraw a waiting group, ready or not, and return it.
  def cancel(group_id)
    group = @groups[group_id]
    raise TitoError, "group #{group_id} is not in the queue" if group.nil?

    remove(group)
    group
  end

  # Withdraw every waiting group, in arrival order, and return them.
  def clear
    cleared = @groups.values
    @groups = {}
    @member_index = {}
    cleared
  end

  # Waiting groups, in arrival order.
  def groups
    @groups.values
  end

  def size
    @groups.size
  end

  def contains?(member)
    @member_index.key?(member)
  end

  def to_s
    "TitoQueue(strict_order=#{@strict_order}, groups=#{@groups.size})"
  end

  private

  def remove(group)
    @groups.delete(group.group_id)
    group.members.each { |member| @member_index.delete(member) }
  end
end

# Format a boolean the same way in every example language.
def flag(value)
  value ? 'true' : 'false'
end

# Format an optional group, as returned by peek and release.
def show(group)
  group.nil? ? 'waiting' : group.to_s
end

# Format the group lists returned by release_all and clear.
def show_all(groups)
  return 'none' if groups.empty?

  groups.map(&:to_s).join(', ')
end

# Format the group ids of the waiting groups.
def show_ids(groups)
  return 'none' if groups.empty?

  groups.map(&:group_id).join(' ')
end

# Head-of-line FIFO: party-2 waits behind party-1 until it departs.
def strict_order_demo
  puts '-- strict order --'
  queue = TitoQueue.new
  puts "admit #{queue.admit('party-1', %w[ann bob])}"
  puts "admit #{queue.admit('party-2', %w[cy])}"
  puts "len #{queue.size}, groups #{show_ids(queue.groups)}"
  puts "contains ann #{flag(queue.contains?('ann'))}, contains zoe #{flag(queue.contains?('zoe'))}"

  party1 = queue.group_of('bob')
  puts "group_of bob -> #{party1.group_id}"
  puts "party-1: size #{party1.size}, contains ann #{flag(party1.contains?('ann'))}, " \
       "contains zoe #{flag(party1.contains?('zoe'))}"

  puts "mark_ready ann -> group ready #{flag(queue.mark_ready('ann'))}"
  puts "party-1: #{party1.ready_count}/#{party1.size} ready [#{party1.ready_members.join(' ')}] " \
       "waiting [#{party1.waiting_members.join(' ')}] is_ready #{flag(party1.ready?)}"
  puts "peek -> #{show(queue.peek)}"
  puts "release -> #{show(queue.release)}"

  puts "party-1.mark_ready bob -> group ready #{flag(party1.mark_ready('bob'))}"
  puts "party-1: #{party1.ready_count}/#{party1.size} ready [#{party1.ready_members.join(' ')}] " \
       "waiting [#{party1.waiting_members.join(' ')}] is_ready #{flag(party1.ready?)}"
  puts "peek -> #{show(queue.peek)}"
  puts "release -> #{show(queue.release)}"

  puts "mark_group_ready party-2 -> #{flag(queue.mark_group_ready('party-2'))}"
  puts "release_all -> #{show_all(queue.release_all)}"
  puts "len #{queue.size}"
end

# Without strict order, ready party-4 leaves ahead of waiting party-3.
def relaxed_order_demo
  puts '-- relaxed order --'
  queue = TitoQueue.new(strict_order: false)
  puts "strict_order #{flag(queue.strict_order)}"
  puts "admit #{queue.admit('party-3', %w[dee eli])}"
  puts "admit #{queue.admit('party-4', %w[fay])}"

  puts "mark_group_ready party-4 -> #{flag(queue.mark_group_ready('party-4'))}"
  puts "peek -> #{show(queue.peek)}"
  puts "release -> #{show(queue.release)}"

  puts "mark_ready dee -> group ready #{flag(queue.mark_ready('dee'))}"
  puts "release -> #{show(queue.release)}"
  puts "mark_ready eli -> group ready #{flag(queue.mark_ready('eli'))}"
  puts "release_all -> #{show_all(queue.release_all)}"
  puts "len #{queue.size}"
end

# Cancelling is the only way a group leaves before it is fully ready.
def cancel_and_clear_demo
  puts '-- cancel and clear --'
  queue = TitoQueue.new
  puts "admit #{queue.admit('party-5', %w[gil hal])}"
  puts "admit #{queue.admit('party-6', %w[ivy])}"
  puts "admit #{queue.admit('party-7', %w[jay])}"

  puts "mark_ready gil -> group ready #{flag(queue.mark_ready('gil'))}"
  cancelled = queue.cancel('party-5')
  puts "cancel party-5 -> #{cancelled} #{cancelled.ready_count}/#{cancelled.size} ready"
  puts "groups #{show_ids(queue.groups)}"
  puts "clear -> #{show_all(queue.clear)}"
  puts "len #{queue.size}, contains ivy #{flag(queue.contains?('ivy'))}"
end

# Run an operation that must fail, and print the reported reason.
def attempt(label)
  yield
rescue TitoError => e
  puts "#{label} -> #{e.message}"
else
  puts "#{label} -> no error"
end

# Every operation that would break the TITO invariants is rejected.
def error_demo
  puts '-- errors --'
  queue = TitoQueue.new
  puts "admit #{queue.admit('party-8', %w[kim])}"

  attempt('admit party-8 [kim]') { queue.admit('party-8', %w[kim]) }
  attempt('admit party-9 []') { queue.admit('party-9', []) }
  attempt('admit party-9 [jay jay]') { queue.admit('party-9', %w[jay jay]) }
  attempt('admit party-9 [kim]') { queue.admit('party-9', %w[kim]) }
  attempt('mark_ready zoe') { queue.mark_ready('zoe') }
  attempt('party-8.mark_ready zoe') { queue.group_of('kim').mark_ready('zoe') }
  attempt('mark_group_ready party-9') { queue.mark_group_ready('party-9') }
  attempt('cancel party-9') { queue.cancel('party-9') }
end

def main
  strict_order_demo
  puts ''
  relaxed_order_demo
  puts ''
  cancel_and_clear_demo
  puts ''
  error_demo
end

main if $PROGRAM_NAME == __FILE__
