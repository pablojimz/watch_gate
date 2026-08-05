#!/bin/bash

# ruleid: connection-string-hardcoded-password
CONN_STR="mongodb://admin:SuperSecret123@db0.example.com/mydb"

# ruleid: connection-string-hardcoded-password
CONN_STR2="postgresql://appuser:hunter2pass@db.internal:5432/app"

# ok: connection-string-hardcoded-password
CONN_STR3="mongodb://${DB_USER}:${DB_PASSWORD}@db0.example.com/mydb"

# ok: connection-string-hardcoded-password
CONN_STR4="mongodb://db0.example.com/mydb"
