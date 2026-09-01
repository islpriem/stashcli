#!/bin/sh
# Refetch contracts/openapi.json from the stashd checkout beside this one. The file is
# vendored, never hand-edited: stashd owns the wire contract.
set -eu
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
source=$(cd -- "$root/.." && pwd)/stashd/contracts/openapi.json
if [ ! -f "$source" ]; then
    echo "no stashd/contracts/openapi.json beside this checkout: $source" >&2
    exit 1
fi
cp "$source" "$root/contracts/openapi.json"
echo "synced $root/contracts/openapi.json"
