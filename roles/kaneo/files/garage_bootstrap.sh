#!/usr/bin/env bash
#
# garage_bootstrap.sh — one-time + re-runnable Garage setup for the
# Kaneo stack.  Apply a cluster layout, ensure the bucket exists,
# import the vault-supplied access key (or print a new one if the
# vault entries are empty so they can be added).
#
# Run this on the host after `make deploy-kaneo` brings the stack
# up.  Re-running is safe — each step is gated on the current state.
#
# Variables (set via env before running, or edit defaults below):
#   KANEO_GARAGE_CONTAINER    default: kaneo-garage
#   KANEO_S3_BUCKET           default: kaneo-uploads
#   KANEO_S3_ACCESS_KEY_ID    if set, import this key; if empty, a new
#                             one is generated and printed for vault
#   KANEO_S3_SECRET_ACCESS_KEY  paired secret for import
#   KANEO_CLIENT_ORIGIN       default: https://kaneo.atelier.house
#                             CORS origin allowed for presigned PUTs
#   KANEO_BACKEND_NETWORK     default: backend-internal
#                             docker network shared with kaneo-garage, used
#                             by the one-shot aws-cli container in step 5

set -euo pipefail

CONTAINER="${KANEO_GARAGE_CONTAINER:-kaneo-garage}"
BUCKET="${KANEO_S3_BUCKET:-kaneo-uploads}"
KEY_NAME="${KANEO_S3_KEY_NAME:-kaneo-prod-key}"
CLIENT_ORIGIN="${KANEO_CLIENT_ORIGIN:-https://kaneo.atelier.house}"
REGION="${KANEO_S3_REGION:-garage}"
# The compose file declares `backend` as an external network named
# backend-internal; compose does not prefix external networks, so there is no
# `kaneo_backend` to attach to.
BACKEND_NETWORK="${KANEO_BACKEND_NETWORK:-backend-internal}"

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
#   a) Vault has KANEO_S3_ACCESS_KEY_ID + _SECRET — import them so
#      Ansible's kaneo.env values are the live credentials.
#   b) Vault is empty — generate a new key and print it for the
#      operator to add to the vault, then re-run this script with the
#      env vars set to import them.
if [ -n "${KANEO_S3_ACCESS_KEY_ID:-}" ] && [ -n "${KANEO_S3_SECRET_ACCESS_KEY:-}" ]; then
  if g key info "${KANEO_S3_ACCESS_KEY_ID}" >/dev/null 2>&1; then
    echo "Key ${KANEO_S3_ACCESS_KEY_ID} already imported — skipping."
  else
    echo "Importing access key ${KANEO_S3_ACCESS_KEY_ID}..."
    g key import --yes \
      --name "${KEY_NAME}" \
      "${KANEO_S3_ACCESS_KEY_ID}" \
      "${KANEO_S3_SECRET_ACCESS_KEY}"
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
ACCESS_KEY_ID="${KANEO_S3_ACCESS_KEY_ID:-$(g key info "${KEY_NAME}" | awk '/Key ID:/ {print $3}')}"
echo "Granting ${ACCESS_KEY_ID} read+write+owner on ${BUCKET}..."
g bucket allow --read --write --owner "${BUCKET}" --key "${ACCESS_KEY_ID}"

# Step 5 — CORS for the SPA's cross-origin presigned PUT. Without this the
# browser refuses the upload before it ever reaches Garage. Garage v2.3.0's
# CLI has no `bucket set-cors` — CORS is an S3-API config (PutBucketCors), so
# this runs aws-cli as a one-shot container on the shared backend network; it
# depends neither on the private Kaneo image's internals nor on a host
# aws-cli. The Ansible deploy also applies this idempotently; this keeps the
# standalone script correct for a manual first-time bootstrap. Garage 2.3.0
# compares allowed header names case-sensitively, while browser preflights
# serialize them in lowercase.
echo "Setting CORS on ${BUCKET} for ${CLIENT_ORIGIN}..."
SECRET="${KANEO_S3_SECRET_ACCESS_KEY:?need secret for CORS step}"
CORS_JSON="$(printf '{"CORSRules":[{"AllowedOrigins":["%s"],"AllowedMethods":["GET","PUT","POST","DELETE"],"AllowedHeaders":["content-type"],"ExposeHeaders":["ETag","Accept-Ranges","Content-Range"]}]}' "${CLIENT_ORIGIN}")"
docker run --rm \
  --network "${BACKEND_NETWORK}" \
  -e AWS_ACCESS_KEY_ID="${ACCESS_KEY_ID}" \
  -e AWS_SECRET_ACCESS_KEY="${SECRET}" \
  amazon/aws-cli:latest s3api put-bucket-cors \
  --bucket "${BUCKET}" \
  --endpoint-url http://kaneo-garage:3900 \
  --region "${REGION}" \
  --cors-configuration "${CORS_JSON}"

echo "Garage bootstrap done."
