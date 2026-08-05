#!/bin/bash

# ruleid: mysql-jdbc-autodeserialize
JDBC_URL="jdbc:mysql://db.example.com:3306/mydb?autoDeserialize=true"

# ok: mysql-jdbc-autodeserialize
JDBC_URL2="jdbc:mysql://db.example.com:3306/mydb?useSSL=true"
