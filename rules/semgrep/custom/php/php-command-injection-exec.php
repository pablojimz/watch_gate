<?php

function bad1($userInput) {
    // ruleid: php-command-injection-exec
    system($userInput);
}

function bad2($filename) {
    // ruleid: php-command-injection-exec
    exec("ls " . $filename, $output);
}

function bad3($userInput) {
    // ruleid: php-command-injection-exec
    shell_exec($userInput);
}

function bad4($userInput) {
    // ruleid: php-command-injection-exec
    passthru($userInput);
}

function ok1() {
    // ok: php-command-injection-exec
    system("uptime");
}

function ok2() {
    // ok: php-command-injection-exec
    exec("ls -la", $output);
}
