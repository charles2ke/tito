/* Together In Together Out - C example.
 *
 * Run: gcc -std=c11 -O2 -o /tmp/tito_c examples/tito_example.c && /tmp/tito_c
 */

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define MAX_GROUPS 16
#define MAX_MEMBERS 8
#define MAX_NAME 32
#define MAX_MSG 128

/* A set of members that entered the queue together. A group is only ever
 * released as a whole: it departs once every member has been marked ready. */
typedef struct {
    char id[MAX_NAME];
    char members[MAX_MEMBERS][MAX_NAME];
    int ready[MAX_MEMBERS]; /* parallel to members: 1 once that member is ready */
    int member_count;
    int ready_count;
} Group;

/* A queue that admits and releases members group by group.
 *
 * strict_order = 1 (the default) is head-of-line FIFO: only the oldest waiting
 * group may depart. strict_order = 0 lets any fully ready group depart, still
 * oldest first, so a waiting group does not block ready groups behind it.
 *
 * With no exceptions, operations report failure with a return code and leave a
 * human-readable reason in error. Groups are held in arrival order; removing
 * one from the middle simply shifts the tail down. */
typedef struct {
    Group groups[MAX_GROUPS];
    int group_count;
    int strict_order;
    char error[MAX_MSG];
} TitoQueue;

static void tito_init(TitoQueue *queue, int strict_order) {
    queue->group_count = 0;
    queue->strict_order = strict_order;
    queue->error[0] = '\0';
}

static int name_fits(const char *name) {
    return strlen(name) < MAX_NAME;
}

/* Bounded copy that always terminates; callers validate names fit first. */
static void copy_name(char *dst, const char *src) {
    size_t i = 0;

    while (src[i] != '\0' && i + 1 < MAX_NAME) {
        dst[i] = src[i];
        i++;
    }
    dst[i] = '\0';
}

/* Append text to buf without overflowing it; *len tracks the current length. */
static void append(char *buf, size_t cap, size_t *len, const char *text) {
    for (const char *c = text; *c != '\0' && *len + 1 < cap; c++) {
        buf[(*len)++] = *c;
    }
    buf[*len] = '\0';
}

static int group_len(const Group *group) {
    return group->member_count;
}

static int group_is_ready(const Group *group) {
    return group->ready_count == group->member_count;
}

static int group_contains(const Group *group, const char *member) {
    for (int i = 0; i < group->member_count; i++) {
        if (strcmp(group->members[i], member) == 0) {
            return 1;
        }
    }
    return 0;
}

/* Marks member ready. Returns 1 if the whole group is now ready, 0 if not, or
 * -1 if member does not belong to the group (reason written to err). */
static int group_mark_ready(Group *group, const char *member, char *err, size_t err_size) {
    for (int i = 0; i < group->member_count; i++) {
        if (strcmp(group->members[i], member) == 0) {
            if (!group->ready[i]) {
                group->ready[i] = 1;
                group->ready_count++;
            }
            return group_is_ready(group);
        }
    }
    snprintf(err, err_size, "%s is not a member of group %s", member, group->id);
    return -1;
}

static Group *tito_group_of(TitoQueue *queue, const char *member) {
    for (int g = 0; g < queue->group_count; g++) {
        if (group_contains(&queue->groups[g], member)) {
            return &queue->groups[g];
        }
    }
    return NULL;
}

static int tito_len(const TitoQueue *queue) {
    return queue->group_count;
}

static int tito_contains(TitoQueue *queue, const char *member) {
    return tito_group_of(queue, member) != NULL;
}

/* Admit members as one group. Returns the admitted group, or NULL on failure
 * with the reason written to queue->error. */
static Group *tito_admit(TitoQueue *queue, const char *id, const char *const *members, int count) {
    Group *group;

    if (count <= 0) {
        snprintf(queue->error, sizeof queue->error,
                 "group %s must contain at least one member", id);
        return NULL;
    }
    if (!name_fits(id)) {
        snprintf(queue->error, sizeof queue->error, "group %s is too long", id);
        return NULL;
    }
    for (int i = 0; i < count; i++) {
        if (!name_fits(members[i])) {
            snprintf(queue->error, sizeof queue->error, "member %s is too long", members[i]);
            return NULL;
        }
    }
    for (int i = 0; i < count; i++) {
        for (int j = 0; j < i; j++) {
            if (strcmp(members[j], members[i]) == 0) {
                snprintf(queue->error, sizeof queue->error,
                         "group %s contains duplicate members", id);
                return NULL;
            }
        }
    }
    if (count > MAX_MEMBERS || queue->group_count == MAX_GROUPS) {
        snprintf(queue->error, sizeof queue->error, "group %s does not fit in the queue", id);
        return NULL;
    }
    for (int g = 0; g < queue->group_count; g++) {
        if (strcmp(queue->groups[g].id, id) == 0) {
            snprintf(queue->error, sizeof queue->error, "group %s is already in the queue", id);
            return NULL;
        }
    }
    {
        size_t len = 0;
        int queued = 0;

        for (int i = 0; i < count; i++) {
            if (tito_contains(queue, members[i])) {
                if (!queued) {
                    queue->error[0] = '\0';
                    append(queue->error, sizeof queue->error, &len, "members already in the queue:");
                    queued = 1;
                }
                append(queue->error, sizeof queue->error, &len, " ");
                append(queue->error, sizeof queue->error, &len, members[i]);
            }
        }
        if (queued) {
            return NULL;
        }
    }

    group = &queue->groups[queue->group_count++];
    copy_name(group->id, id);
    group->member_count = count;
    group->ready_count = 0;
    for (int i = 0; i < count; i++) {
        copy_name(group->members[i], members[i]);
        group->ready[i] = 0;
    }
    return group;
}

/* Mark a queued member ready. Returns 1 if its group is now ready, 0 if not,
 * or -1 if the member is not queued (reason written to queue->error). */
static int tito_mark_ready(TitoQueue *queue, const char *member) {
    Group *group = tito_group_of(queue, member);

    if (group == NULL) {
        snprintf(queue->error, sizeof queue->error, "%s is not in the queue", member);
        return -1;
    }
    return group_mark_ready(group, member, queue->error, sizeof queue->error);
}

/* Mark every member of a queued group ready. Returns 0 on success, -1 if the
 * group is not queued (reason written to queue->error). */
static int tito_mark_group_ready(TitoQueue *queue, const char *id) {
    for (int g = 0; g < queue->group_count; g++) {
        Group *group = &queue->groups[g];

        if (strcmp(group->id, id) == 0) {
            for (int i = 0; i < group->member_count; i++) {
                group->ready[i] = 1;
            }
            group->ready_count = group->member_count;
            return 0;
        }
    }
    snprintf(queue->error, sizeof queue->error, "group %s is not in the queue", id);
    return -1;
}

/* Index of the next group that would be released, or -1 if none can depart. */
static int tito_peek_index(const TitoQueue *queue) {
    if (queue->group_count == 0) {
        return -1;
    }
    if (queue->strict_order) {
        /* The head of the line blocks every group behind it. */
        return group_is_ready(&queue->groups[0]) ? 0 : -1;
    }
    for (int g = 0; g < queue->group_count; g++) {
        if (group_is_ready(&queue->groups[g])) {
            return g;
        }
    }
    return -1;
}

/* The next group that would be released, without releasing it, or NULL. */
static const Group *tito_peek(const TitoQueue *queue) {
    int index = tito_peek_index(queue);

    return index < 0 ? NULL : &queue->groups[index];
}

static void tito_remove_at(TitoQueue *queue, int index) {
    for (int g = index; g < queue->group_count - 1; g++) {
        queue->groups[g] = queue->groups[g + 1];
    }
    queue->group_count--;
}

/* Release the next fully ready group into *out. Returns 1 if a group departed,
 * 0 if none can. */
static int tito_release(TitoQueue *queue, Group *out) {
    int index = tito_peek_index(queue);

    if (index < 0) {
        return 0;
    }
    *out = queue->groups[index];
    tito_remove_at(queue, index);
    return 1;
}

/* Release every group that can currently depart into out, in order. */
static int tito_release_all(TitoQueue *queue, Group *out, int capacity) {
    int count = 0;

    while (count < capacity && tito_release(queue, &out[count])) {
        count++;
    }
    return count;
}

/* Withdraw a waiting group, ready or not, into *out. Returns 0 on success, -1
 * if the group is not queued (reason written to queue->error). */
static int tito_cancel(TitoQueue *queue, const char *id, Group *out) {
    for (int g = 0; g < queue->group_count; g++) {
        if (strcmp(queue->groups[g].id, id) == 0) {
            *out = queue->groups[g];
            tito_remove_at(queue, g);
            return 0;
        }
    }
    snprintf(queue->error, sizeof queue->error, "group %s is not in the queue", id);
    return -1;
}

/* Withdraw every waiting group, in arrival order, into out. */
static int tito_clear(TitoQueue *queue, Group *out, int capacity) {
    int count = queue->group_count < capacity ? queue->group_count : capacity;

    for (int g = 0; g < count; g++) {
        out[g] = queue->groups[g];
    }
    queue->group_count = 0;
    return count;
}

static const char *flag(int value) {
    return value ? "true" : "false";
}

/* Format a group as "id [m1 m2 ...]". */
static void format_group(const Group *group, char *buf, size_t cap) {
    size_t len = 0;

    buf[0] = '\0';
    append(buf, cap, &len, group->id);
    append(buf, cap, &len, " [");
    for (int i = 0; i < group->member_count; i++) {
        if (i != 0) {
            append(buf, cap, &len, " ");
        }
        append(buf, cap, &len, group->members[i]);
    }
    append(buf, cap, &len, "]");
}

/* Format the members whose ready flag equals want, space separated. */
static void format_members(const Group *group, int want, char *buf, size_t cap) {
    size_t len = 0;
    int first = 1;

    buf[0] = '\0';
    for (int i = 0; i < group->member_count; i++) {
        if (group->ready[i] == want) {
            if (!first) {
                append(buf, cap, &len, " ");
            }
            append(buf, cap, &len, group->members[i]);
            first = 0;
        }
    }
}

/* Format an optional group, as returned by peek() and release(). */
static void format_optional(const Group *group, char *buf, size_t cap) {
    if (group == NULL) {
        copy_name(buf, "waiting");
    } else {
        format_group(group, buf, cap);
    }
}

/* Format a list of groups as "g1, g2, ...", or "none" when empty. */
static void format_group_list(const Group *groups, int count, char *buf, size_t cap) {
    size_t len = 0;

    if (count == 0) {
        copy_name(buf, "none");
        return;
    }
    buf[0] = '\0';
    for (int g = 0; g < count; g++) {
        char one[MAX_MSG];

        if (g != 0) {
            append(buf, cap, &len, ", ");
        }
        format_group(&groups[g], one, sizeof one);
        append(buf, cap, &len, one);
    }
}

/* Format the ids of the waiting groups, space separated, or "none" when empty. */
static void format_group_ids(const TitoQueue *queue, char *buf, size_t cap) {
    size_t len = 0;

    if (queue->group_count == 0) {
        copy_name(buf, "none");
        return;
    }
    buf[0] = '\0';
    for (int g = 0; g < queue->group_count; g++) {
        if (g != 0) {
            append(buf, cap, &len, " ");
        }
        append(buf, cap, &len, queue->groups[g].id);
    }
}

static void print_state(const Group *group) {
    char ready[MAX_MSG];
    char waiting[MAX_MSG];

    format_members(group, 1, ready, sizeof ready);
    format_members(group, 0, waiting, sizeof waiting);
    printf("%s: %d/%d ready [%s] waiting [%s] is_ready %s\n", group->id,
           group->ready_count, group_len(group), ready, waiting, flag(group_is_ready(group)));
}

/* Report an operation that must fail, mirroring the reference attempt() helper. */
static void report(const char *label, int failed, const char *message) {
    if (failed) {
        printf("%s -> %s\n", label, message);
    } else {
        printf("%s -> no error\n", label);
    }
}

/* Head-of-line FIFO: party-2 waits behind party-1 until it departs. */
static void strict_order_demo(void) {
    TitoQueue queue;
    Group released;
    Group departed[MAX_GROUPS];
    Group *party1;
    char buf[MAX_MSG];
    int ready;
    int count;

    static const char *const party1_members[] = {"ann", "bob"};
    static const char *const party2_members[] = {"cy"};

    printf("-- strict order --\n");
    tito_init(&queue, 1);

    format_group(tito_admit(&queue, "party-1", party1_members, 2), buf, sizeof buf);
    printf("admit %s\n", buf);
    format_group(tito_admit(&queue, "party-2", party2_members, 1), buf, sizeof buf);
    printf("admit %s\n", buf);

    format_group_ids(&queue, buf, sizeof buf);
    printf("len %d, groups %s\n", tito_len(&queue), buf);
    printf("contains ann %s, contains zoe %s\n", flag(tito_contains(&queue, "ann")),
           flag(tito_contains(&queue, "zoe")));

    party1 = tito_group_of(&queue, "bob");
    printf("group_of bob -> %s\n", party1->id);
    printf("party-1: size %d, contains ann %s, contains zoe %s\n", group_len(party1),
           flag(group_contains(party1, "ann")), flag(group_contains(party1, "zoe")));

    ready = tito_mark_ready(&queue, "ann");
    printf("mark_ready ann -> group ready %s\n", flag(ready == 1));
    print_state(party1);
    format_optional(tito_peek(&queue), buf, sizeof buf);
    printf("peek -> %s\n", buf);
    format_optional(tito_release(&queue, &released) ? &released : NULL, buf, sizeof buf);
    printf("release -> %s\n", buf);

    ready = group_mark_ready(party1, "bob", queue.error, sizeof queue.error);
    printf("party-1.mark_ready bob -> group ready %s\n", flag(ready == 1));
    print_state(party1);
    format_optional(tito_peek(&queue), buf, sizeof buf);
    printf("peek -> %s\n", buf);
    format_optional(tito_release(&queue, &released) ? &released : NULL, buf, sizeof buf);
    printf("release -> %s\n", buf);

    printf("mark_group_ready party-2 -> %s\n", flag(tito_mark_group_ready(&queue, "party-2") == 0));
    count = tito_release_all(&queue, departed, MAX_GROUPS);
    format_group_list(departed, count, buf, sizeof buf);
    printf("release_all -> %s\n", buf);
    printf("len %d\n", tito_len(&queue));
}

/* Without strict order, ready party-4 leaves ahead of waiting party-3. */
static void relaxed_order_demo(void) {
    TitoQueue queue;
    Group released;
    Group departed[MAX_GROUPS];
    char buf[MAX_MSG];
    int count;

    static const char *const party3_members[] = {"dee", "eli"};
    static const char *const party4_members[] = {"fay"};

    printf("-- relaxed order --\n");
    tito_init(&queue, 0);
    printf("strict_order %s\n", flag(queue.strict_order));

    format_group(tito_admit(&queue, "party-3", party3_members, 2), buf, sizeof buf);
    printf("admit %s\n", buf);
    format_group(tito_admit(&queue, "party-4", party4_members, 1), buf, sizeof buf);
    printf("admit %s\n", buf);

    printf("mark_group_ready party-4 -> %s\n", flag(tito_mark_group_ready(&queue, "party-4") == 0));
    format_optional(tito_peek(&queue), buf, sizeof buf);
    printf("peek -> %s\n", buf);
    format_optional(tito_release(&queue, &released) ? &released : NULL, buf, sizeof buf);
    printf("release -> %s\n", buf);

    printf("mark_ready dee -> group ready %s\n", flag(tito_mark_ready(&queue, "dee") == 1));
    format_optional(tito_release(&queue, &released) ? &released : NULL, buf, sizeof buf);
    printf("release -> %s\n", buf);
    printf("mark_ready eli -> group ready %s\n", flag(tito_mark_ready(&queue, "eli") == 1));
    count = tito_release_all(&queue, departed, MAX_GROUPS);
    format_group_list(departed, count, buf, sizeof buf);
    printf("release_all -> %s\n", buf);
    printf("len %d\n", tito_len(&queue));
}

/* Cancelling is the only way a group leaves before it is fully ready. */
static void cancel_and_clear_demo(void) {
    TitoQueue queue;
    Group cancelled;
    Group cleared[MAX_GROUPS];
    char buf[MAX_MSG];
    int count;

    static const char *const party5_members[] = {"gil", "hal"};
    static const char *const party6_members[] = {"ivy"};
    static const char *const party7_members[] = {"jay"};

    printf("-- cancel and clear --\n");
    tito_init(&queue, 1);

    format_group(tito_admit(&queue, "party-5", party5_members, 2), buf, sizeof buf);
    printf("admit %s\n", buf);
    format_group(tito_admit(&queue, "party-6", party6_members, 1), buf, sizeof buf);
    printf("admit %s\n", buf);
    format_group(tito_admit(&queue, "party-7", party7_members, 1), buf, sizeof buf);
    printf("admit %s\n", buf);

    printf("mark_ready gil -> group ready %s\n", flag(tito_mark_ready(&queue, "gil") == 1));
    tito_cancel(&queue, "party-5", &cancelled);
    format_group(&cancelled, buf, sizeof buf);
    printf("cancel party-5 -> %s %d/%d ready\n", buf, cancelled.ready_count, cancelled.member_count);
    format_group_ids(&queue, buf, sizeof buf);
    printf("groups %s\n", buf);
    count = tito_clear(&queue, cleared, MAX_GROUPS);
    format_group_list(cleared, count, buf, sizeof buf);
    printf("clear -> %s\n", buf);
    printf("len %d, contains ivy %s\n", tito_len(&queue), flag(tito_contains(&queue, "ivy")));
}

/* Every operation that would break the TITO invariants is rejected. */
static void error_demo(void) {
    TitoQueue queue;
    Group *party8;
    Group cancelled;
    char buf[MAX_MSG];
    int result;

    static const char *const kim[] = {"kim"};
    static const char *const jay_jay[] = {"jay", "jay"};

    printf("-- errors --\n");
    tito_init(&queue, 1);
    format_group(tito_admit(&queue, "party-8", kim, 1), buf, sizeof buf);
    printf("admit %s\n", buf);

    report("admit party-8 [kim]", tito_admit(&queue, "party-8", kim, 1) == NULL, queue.error);
    report("admit party-9 []", tito_admit(&queue, "party-9", NULL, 0) == NULL, queue.error);
    report("admit party-9 [jay jay]", tito_admit(&queue, "party-9", jay_jay, 2) == NULL, queue.error);
    report("admit party-9 [kim]", tito_admit(&queue, "party-9", kim, 1) == NULL, queue.error);
    report("mark_ready zoe", tito_mark_ready(&queue, "zoe") < 0, queue.error);

    party8 = tito_group_of(&queue, "kim");
    result = group_mark_ready(party8, "zoe", queue.error, sizeof queue.error);
    report("party-8.mark_ready zoe", result < 0, queue.error);

    report("mark_group_ready party-9", tito_mark_group_ready(&queue, "party-9") != 0, queue.error);
    report("cancel party-9", tito_cancel(&queue, "party-9", &cancelled) != 0, queue.error);
}

int main(void) {
    strict_order_demo();
    printf("\n");
    relaxed_order_demo();
    printf("\n");
    cancel_and_clear_demo();
    printf("\n");
    error_demo();
    return 0;
}
