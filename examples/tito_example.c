/* Together In Together Out - C example.
 *
 * Run: gcc -std=c11 -O2 -o /tmp/tito_c examples/tito_example.c && /tmp/tito_c
 */

#include <stdio.h>
#include <string.h>

#define MAX_GROUPS 16
#define MAX_MEMBERS 8
#define MAX_NAME 32

typedef struct {
    char id[MAX_NAME];
    char members[MAX_MEMBERS][MAX_NAME];
    int ready[MAX_MEMBERS];
    int member_count;
} Group;

/* Minimal strict-order (head-of-line FIFO) TITO queue. */
typedef struct {
    Group groups[MAX_GROUPS];
    int head;  /* index of the oldest waiting group */
    int tail;  /* one past the newest waiting group */
    int group_count;
} TitoQueue;

static void tito_init(TitoQueue *queue) {
    queue->head = 0;
    queue->tail = 0;
    queue->group_count = 0;
}

/* Returns 0 on success, -1 if the group does not fit or a name is too long. */
static int tito_admit(TitoQueue *queue, const char *id, const char *const *members, int count) {
    Group *group;
    int i;

    if (count <= 0 || count > MAX_MEMBERS || queue->group_count == MAX_GROUPS) {
        return -1;
    }
    if (strlen(id) >= MAX_NAME) {
        return -1;
    }
    for (i = 0; i < count; i++) {
        if (strlen(members[i]) >= MAX_NAME) {
            return -1;
        }
        for (int j = 0; j < i; j++) {
            if (strcmp(members[j], members[i]) == 0) {
                return -1;
            }
        }
        for (int g = 0; g < queue->group_count; g++) {
            const Group *queued = &queue->groups[(queue->head + g) % MAX_GROUPS];
            for (int j = 0; j < queued->member_count; j++) {
                if (strcmp(queued->members[j], members[i]) == 0) {
                    return -1;
                }
            }
        }
    }
    group = &queue->groups[queue->tail];
    snprintf(group->id, MAX_NAME, "%s", id);
    group->member_count = count;
    for (i = 0; i < count; i++) {
        snprintf(group->members[i], MAX_NAME, "%s", members[i]);
        group->ready[i] = 0;
    }
    queue->tail = (queue->tail + 1) % MAX_GROUPS;
    queue->group_count++;
    return 0;
}

/* Returns 0 on success, -1 if the member is not queued. */
static int tito_mark_ready(TitoQueue *queue, const char *member) {
    int g, i;

    for (g = 0; g < queue->group_count; g++) {
        Group *group = &queue->groups[(queue->head + g) % MAX_GROUPS];
        for (i = 0; i < group->member_count; i++) {
            if (strcmp(group->members[i], member) == 0) {
                group->ready[i] = 1;
                return 0;
            }
        }
    }
    return -1;
}

/* Returns the head group, or NULL while it is not fully ready. */
static const Group *tito_release(TitoQueue *queue) {
    Group *group;
    int i;

    if (queue->group_count == 0) {
        return NULL;
    }
    group = &queue->groups[queue->head];
    for (i = 0; i < group->member_count; i++) {
        if (!group->ready[i]) {
            return NULL;
        }
    }
    queue->head = (queue->head + 1) % MAX_GROUPS;
    queue->group_count--;
    return group;
}

static void print_group(const Group *group) {
    int i;

    printf("release -> %s [", group->id);
    for (i = 0; i < group->member_count; i++) {
        printf("%s%s", i == 0 ? "" : " ", group->members[i]);
    }
    printf("]\n");
}

int main(void) {
    static const char *const party1[] = {"ann", "bob"};
    static const char *const party2[] = {"cy"};
    static const char *const arrivals[] = {"ann", "bob", "cy"};
    TitoQueue queue;
    int i;

    tito_init(&queue);

    if (tito_admit(&queue, "party-1", party1, 2) != 0) {
        return 1;
    }
    printf("admit party-1: ann, bob\n");
    if (tito_admit(&queue, "party-2", party2, 1) != 0) {
        return 1;
    }
    printf("admit party-2: cy\n");

    for (i = 0; i < 3; i++) {
        const Group *released;

        if (tito_mark_ready(&queue, arrivals[i]) != 0) {
            return 1;
        }
        printf("ready %s\n", arrivals[i]);
        released = tito_release(&queue);
        if (released == NULL) {
            printf("release -> waiting\n");
        } else {
            print_group(released);
        }
    }
    return 0;
}
