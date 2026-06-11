#!/usr/bin/env bash
#
# garage_bootstrap.sh — one-time + re-runnable Garage setup for the
# Kizuna stack.  Apply a cluster layout, ensure the bucket exists,
# import the vault-supplied access key (or print a new one if the
# vault entries are empty so they can be added).
#
# Run this on the host after `make deploy-kizuna` brings the stack
# up.  Re-running is safe — each step is gated on the current state.
#
# Variables (set via env before running, or edit defaults below):
#   KIZUNA_GARAGE_CONTAINER  default: kizuna-garage
#   KIZUNA_S3_BUCKET         default: kizuna
#   KIZUNA_S3_ACCESS_KEY_ID  if set, import this key; if empty, a new
#                            one is generated and printed for vault
#   KIZUNA_S3_SECRET_ACCESS_KEY  paired secret for import
#   KIZUNA_SPA_ORIGIN        default: https://kizuna.fm
#                            CORS origin allowed for presigned PUTs

set -euo pipefail

CONTAINER="${KIZUNA_GARAGE_CONTAINER:-kizuna-garage}"
BUCKET="${KIZUNA_S3_BUCKET:-kizuna}"
KEY_NAME="${KIZUNA_S3_KEY_NAME:-kizuna-prod-key}"
SPA_ORIGIN="${KIZUNA_SPA_ORIGIN:-https://kizuna.fm}"

g() { docker exec "${CONTAINER}" /garage "$@"; }

echo "Waiting for Garage container ${CONTAINER}..."
for i in $(seq 1 30); do
  if docker exec "${CONTAINER}" /garage --help >/dev/null 2>&1; then
    echo "  up."
    break
  fi
  [ "$i" -eq 30 ] && { echo "  Garage did not respond after 30s." >&2; exit 1; }
  sleep 1
done

# Step 1 — cluster layout.  Garage refuses S3 traffic until a layout
# is applied.  Single-node deploys still need this.
if ! g status | grep -qE 'No nodes currently in layout|Healthy nodes'; then :; fi
if ! g status | grep -q '==== HEALTHY NODES ===='; then
  echo "Cluster status unreadable — aborting." >&2
  g status >&2 || true
  exit 1
fi

# layout show prints "No nodes currently have a role" when the layout
# has never been applied. assign-then-apply is idempotent here because
# we gate on that exact string; once applied, subsequent runs no-op.
if g layout show 2>&1 | grep -q 'No nodes currently have a role'; then
  NODE_ID="$(g node id -q | cut -d@ -f1)"
  echo "Assigning layout to node ${NODE_ID}..."
  g layout assign -z dc1 -c 1G "${NODE_ID}"
  g layout apply --version 1
else
  echo "Layout already applied — skipping."
fi

# Step 2 — bucket.
if g bucket info "${BUCKET}" >/dev/null 2>&1; then
  echo "Bucket ${BUCKET} exists — skipping create."
else
  echo "Creating bucket ${BUCKET}..."
  g bucket create "${BUCKET}"
fi

# Step 3 — access key.  Two paths:
#   a) Vault has KIZUNA_S3_ACCESS_KEY_ID + _SECRET — import them so
#      Ansible's api.env values are the live credentials.
#   b) Vault is empty — generate a new key and print it for the
#      operator to add to the vault, then re-run this script with the
#      env vars set to import them.
if [ -n "${KIZUNA_S3_ACCESS_KEY_ID:-}" ] && [ -n "${KIZUNA_S3_SECRET_ACCESS_KEY:-}" ]; then
  if g key info "${KIZUNA_S3_ACCESS_KEY_ID}" >/dev/null 2>&1; then
    echo "Key ${KIZUNA_S3_ACCESS_KEY_ID} already imported — skipping."
  else
    echo "Importing access key ${KIZUNA_S3_ACCESS_KEY_ID}..."
    g key import --yes \
      --name "${KEY_NAME}" \
      "${KIZUNA_S3_ACCESS_KEY_ID}" \
      "${KIZUNA_S3_SECRET_ACCESS_KEY}"
  fi
else
  if g key info "${KEY_NAME}" >/dev/null 2>&1; then
    echo "Key ${KEY_NAME} already exists — re-printing for the vault:"
    g key info --show-secret "${KEY_NAME}"
  else
    echo "No access key provided — generating ${KEY_NAME}..."
    g key create "${KEY_NAME}"
    echo
    echo "Add these to the vault, then re-run this script:"
    g key info --show-secret "${KEY_NAME}"
    exit 0
  fi
fi

# Step 4 — grant the key full access on the bucket.  `allow` is
# additive and idempotent.
ACCESS_KEY_ID="${KIZUNA_S3_ACCESS_KEY_ID:-$(g key info "${KEY_NAME}" | awk '/Key ID:/ {print $3}')}"
echo "Granting ${ACCESS_KEY_ID} read+write+owner on ${BUCKET}..."
g bucket allow --read --write --owner "${BUCKET}" --key "${ACCESS_KEY_ID}"

# Step 5 — CORS for the SPA's cross-origin presigned PUT. Without this the
# browser refuses the upload before it ever reaches Garage. Garage v2.3.0's
# CLI has no `bucket set-cors` — CORS is an S3-API config (PutBucketCors), so
# set it through the API container's aws-sdk client (matches the Ansible role).
# The Ansible deploy also applies this idempotently; this keeps the standalone
# script correct for a manual first-time bootstrap.
echo "Setting CORS on ${BUCKET} for ${SPA_ORIGIN}..."
docker exec kizuna-api bin/rails runner "
  require \"aws-sdk-s3\"
  Aws::S3::Client.new(
    endpoint: ENV.fetch(\"KIZUNA_S3_ENDPOINT\"),
    region: ENV.fetch(\"KIZUNA_S3_REGION\", \"garage\"),
    access_key_id: ENV.fetch(\"KIZUNA_S3_ACCESS_KEY_ID\"),
    secret_access_key: ENV.fetch(\"KIZUNA_S3_SECRET_ACCESS_KEY\"),
    force_path_style: true
  ).put_bucket_cors(
    bucket: ENV.fetch(\"KIZUNA_S3_BUCKET\"),
    cors_configuration: {cors_rules: [{
      allowed_origins: [\"${SPA_ORIGIN}\"],
      allowed_methods: %w[GET PUT POST DELETE],
      allowed_headers: [\"*\"],
      expose_headers: [\"ETag\"]
    }]}
  )
"

echo "Garage bootstrap done."
