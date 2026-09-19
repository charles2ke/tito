# Together In Together Out - Ruby example.
#
# Run: ruby examples/tito_example.rb

# Minimal strict-order (head-of-line FIFO) TITO queue.
class TitoQueue
  def initialize
    @order = []
    @groups = {}
    @group_of = {}
  end

  def admit(group_id, members)
    raise ArgumentError, 'a group must contain at least one member' if members.empty?
    raise ArgumentError, "duplicate group id: #{group_id}" if @groups.key?(group_id)

    ready = {}
    members.each do |member|
      raise ArgumentError, "duplicate member: #{member}" if @group_of.key?(member) || ready.key?(member)

      ready[member] = false
    end
    members.each { |member| @group_of[member] = group_id }
    @groups[group_id] = ready
    @order.push(group_id)
  end

  def mark_ready(member)
    group_id = @group_of[member]
    raise ArgumentError, "unknown member: #{member}" if group_id.nil?

    @groups[group_id][member] = true
  end

  # Release the head group, or nil while it is not fully ready.
  def release
    group_id = @order.first
    return nil if group_id.nil?

    ready = @groups[group_id]
    return nil unless ready.values.all?

    @order.shift
    @groups.delete(group_id)
    members = ready.keys
    members.each { |member| @group_of.delete(member) }
    [group_id, members]
  end
end

def main
  queue = TitoQueue.new

  queue.admit('party-1', %w[ann bob])
  puts 'admit party-1: ann, bob'
  queue.admit('party-2', %w[cy])
  puts 'admit party-2: cy'

  %w[ann bob cy].each do |member|
    queue.mark_ready(member)
    puts "ready #{member}"
    released = queue.release
    if released.nil?
      puts 'release -> waiting'
    else
      group_id, members = released
      puts "release -> #{group_id} [#{members.join(' ')}]"
    end
  end
end

main if $PROGRAM_NAME == __FILE__
