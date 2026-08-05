#include <stdlib.h>

void bad1(size_t count, size_t size) {
    // ruleid: c-integer-overflow-malloc-size
    void *buf = malloc(count * size);
}

void ok1() {
    // ok: c-integer-overflow-malloc-size
    void *buf = malloc(sizeof(int));
}

void ok2(size_t count, size_t size) {
    // ok: c-integer-overflow-malloc-size
    void *buf = calloc(count, size);
}
