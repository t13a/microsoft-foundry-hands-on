#!/bin/sh
# Stages the hosted agent for a code deploy (remote build).
# Remote build gets only the service folder and installs from requirements.txt, so the
# workspace package `catalog` is copied in next to `consultation` (V-12, docs/design.md 11).
set -eu
cd "$(dirname "$0")/.."
out=.build/agent
rm -rf "$out"
mkdir -p "$out"
cp -r agent/src/consultation packages/catalog/src/catalog "$out/"
cp -r agent/content "$out/content"
# Interim: a snapshot of the catalog. Reading it from Blob, as the BFF does, comes in S6.
cp -r data "$out/data"
cp agent/main.py "$out/main.py"
uv export --package consultation --no-emit-workspace --no-dev --no-hashes --frozen --no-header \
  --output-file "$out/requirements.txt" >/dev/null
find "$out" -name __pycache__ -prune -exec rm -rf {} +
echo "staged $out"
