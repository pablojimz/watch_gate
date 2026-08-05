#include <stdlib.h>

void bad1(char *user_input) {
    // ruleid: c-command-injection-system
    system(user_input);
}

void bad2(char *user_input) {
    // ruleid: c-command-injection-system
    FILE *fp = popen(user_input, "r");
}

void ok1() {
    // ok: c-command-injection-system
    system("uptime");
}

void ok2() {
    // ok: c-command-injection-system
    FILE *fp = popen("ls -la", "r");
}
