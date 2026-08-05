#include <unistd.h>
#include <fcntl.h>

void bad1(const char *path) {
    // ruleid: c-toctou-access-open
    access(path, R_OK);
    int fd = open(path, O_RDONLY);
}

void ok1(const char *path) {
    // ok: c-toctou-access-open
    int fd = open(path, O_RDONLY);
}
