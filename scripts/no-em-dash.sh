#!/usr/bin/env bash
# Fails when a tracked file contains the em-dash character (U+2014), which the project
# does not use. The character is written as bytes so that this file passes its own check.
set -euo pipefail
cd "$(dirname "$0")/.."

if git grep -n -I $'\xe2\x80\x94' -- .; then
    echo "Error: the files above contain an em-dash (U+2014). Use other punctuation." >&2
    exit 1
fi
