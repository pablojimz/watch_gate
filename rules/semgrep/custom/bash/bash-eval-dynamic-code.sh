#!/bin/bash

process() {
    local cmd="$1"
    # ruleid: bash-eval-dynamic-code
    eval "$cmd"
}

process2() {
    local cmd="$1"
    # ruleid: bash-eval-dynamic-code
    eval $cmd
}

ok1() {
    # ok: bash-eval-dynamic-code
    eval "echo hello"
}
