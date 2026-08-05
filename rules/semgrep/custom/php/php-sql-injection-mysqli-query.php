<?php

function bad1($mysqli, $userId) {
    // ruleid: php-sql-injection-mysqli-query
    $result = mysqli_query($mysqli, "SELECT * FROM users WHERE id = " . $userId);
}

function bad2($mysqli, $name) {
    // ruleid: php-sql-injection-mysqli-query
    $result = $mysqli->query("SELECT * FROM users WHERE name = '$name'");
}

function ok1($mysqli) {
    // ok: php-sql-injection-mysqli-query
    $result = mysqli_query($mysqli, "SELECT * FROM users");
}

function ok2($mysqli, $userId) {
    $stmt = $mysqli->prepare("SELECT * FROM users WHERE id = ?");
    $stmt->bind_param("i", $userId);
    // ok: php-sql-injection-mysqli-query
    $stmt->execute();
}
