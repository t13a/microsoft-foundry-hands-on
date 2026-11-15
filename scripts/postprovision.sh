#!/bin/sh
# After provisioning (docs/design.md 9.4): upload the catalog CSV if the container has none,
# and create the prompt agent if it does not exist. Never overwrites what is already there.
set -eu
cd "$(dirname "$0")/.."

retry() {
  # New role assignments take a few minutes to apply.
  for i in 1 2 3 4 5 6 7 8 9 10; do
    "$@" && return 0
    echo "retrying in 30s ($i)..." >&2
    sleep 30
  done
  return 1
}

upload_if_missing() {
  name=$1
  exists=$(az storage blob exists --auth-mode login --account-name "$CATALOG_STORAGE_ACCOUNT" \
    --container-name "$CATALOG_CONTAINER" --name "$name" --query exists -o tsv) || return 1
  if [ "$exists" = "true" ]; then
    echo "$name: already in Blob, left as is"
  else
    az storage blob upload --auth-mode login --account-name "$CATALOG_STORAGE_ACCOUNT" \
      --container-name "$CATALOG_CONTAINER" --name "$name" --file "data/$name" --only-show-errors >/dev/null &&
      echo "$name: uploaded"
  fi
}

if [ -z "${CATALOG_STORAGE_ACCOUNT:-}" ]; then
  echo "app layer not provisioned yet; skipping the catalog upload and the prompt agent"
  exit 0
fi

uv run catalog validate data
retry upload_if_missing categories.csv
retry upload_if_missing services.csv
retry uv run python agent/prompt-agent/create.py "${AZURE_AI_MODEL_DEPLOYMENT_NAME:-gpt-5-mini}"
