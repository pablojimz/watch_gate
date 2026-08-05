<?php

function bad1($data) {
    // ruleid: php-insecure-unserialize
    $obj = unserialize($data);
    return $obj;
}

function bad2() {
    $cookie = $_COOKIE['session'];
    // ruleid: php-insecure-unserialize
    $obj = unserialize($cookie);
    return $obj;
}

function ok1() {
    // ok: php-insecure-unserialize
    $obj = unserialize("a:1:{i:0;s:5:\"hello\";}");
    return $obj;
}
