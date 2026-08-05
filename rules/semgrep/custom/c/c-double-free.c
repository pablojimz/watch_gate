#include <stdlib.h>

void bad1(char *ptr) {
    // ruleid: c-double-free
    free(ptr);
    free(ptr);
}

void ok1(char *ptr) {
    // ok: c-double-free
    free(ptr);
    ptr = NULL;
    free(ptr);
}

void ok2(char *ptr, char *other) {
    // ok: c-double-free
    free(ptr);
    ptr = other;
    free(ptr);
}
