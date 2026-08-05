#include <string.h>
#include <stdio.h>

void bad1(char *dst, char *src) {
    // ruleid: c-buffer-overflow-unbounded-copy
    strcpy(dst, src);
}

void bad2(char *dst, char *src) {
    // ruleid: c-buffer-overflow-unbounded-copy
    strcat(dst, src);
}

void bad3(char *dst, char *name) {
    // ruleid: c-buffer-overflow-unbounded-copy
    sprintf(dst, "Hello, %s", name);
}

void bad4(char *dst) {
    // ruleid: c-buffer-overflow-unbounded-copy
    gets(dst);
}

void ok1(char *dst, char *src, size_t n) {
    // ok: c-buffer-overflow-unbounded-copy
    strncpy(dst, src, n);
}

void ok2(char *dst, size_t n) {
    // ok: c-buffer-overflow-unbounded-copy
    fgets(dst, n, stdin);
}
