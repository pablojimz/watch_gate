#!/bin/bash

# ruleid: sqlserver-insecure-connection-encryption
CONN_STR="Server=myserver;Database=mydb;User Id=sa;Password=secret;Encrypt=false"

# ruleid: sqlserver-insecure-connection-encryption
CONN_STR2="Server=myserver;Database=mydb;TrustServerCertificate=true"

# ok: sqlserver-insecure-connection-encryption
CONN_STR3="Server=myserver;Database=mydb;Encrypt=true;TrustServerCertificate=false"
