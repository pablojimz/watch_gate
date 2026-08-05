#include <stdlib.h>

void bad1(char *ptr) {
    // ruleid: c-use-after-free
    free(ptr);
    ptr[0] = 'a';
}

void ok1(char *ptr) {
    // ok: c-use-after-free
    free(ptr);
    ptr = NULL;
    if (ptr != NULL) {
        ptr[0] = 'a';
    }
}

void ok2(char *ptr, char *other) {
    // ok: c-use-after-free
    free(ptr);
    ptr = other;
    ptr[0] = 'a';
}
