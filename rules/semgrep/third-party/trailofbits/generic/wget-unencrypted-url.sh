#!/bin/bash

# ruleid: wget-unencrypted-url
wget http://google.com

# ruleid: wget-unencrypted-url
wget ftp://google.com

# ok: wget-unencrypted-url
wget https://google.com

# ok: wget-unencrypted-url
wget http://localhost

# ok: wget-unencrypted-url
wget http://127.0.0.1

# ok: wget-unencrypted-url
wget http://169.254.169.254

# ok: wget-unencrypted-url
wget http://[fd00:ec2::254]

# ok: wget-unencrypted-url
wget http://metadata.google.internal
