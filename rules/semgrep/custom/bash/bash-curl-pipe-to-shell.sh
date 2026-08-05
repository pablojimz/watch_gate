#!/bin/bash

# ruleid: bash-curl-pipe-to-shell
curl -fsSL https://example.com/install.sh | sh

# ruleid: bash-curl-pipe-to-shell
curl -fsSL https://example.com/install.sh | bash

# ruleid: bash-curl-pipe-to-shell
wget -qO- https://example.com/install.sh | sh

# ok: bash-curl-pipe-to-shell
curl -fsSL https://example.com/install.sh -o install.sh
