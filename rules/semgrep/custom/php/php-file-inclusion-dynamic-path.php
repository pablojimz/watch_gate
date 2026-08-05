<?php

function bad1($page) {
    // ruleid: php-file-inclusion-dynamic-path
    include $page . ".php";
}

function bad2($page) {
    // ruleid: php-file-inclusion-dynamic-path
    require_once $page;
}

function ok1() {
    // ok: php-file-inclusion-dynamic-path
    include "config.php";
}

function ok2() {
    // ok: php-file-inclusion-dynamic-path
    require_once "vendor/autoload.php";
}
