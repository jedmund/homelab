#!/usr/bin/env bash
#
# garage_bootstrap.sh — one-time + re-runnable setup for feederhub's
# dedicated Garage.  Apply the single-node cluster layout, ensure the
# cat-photo bucket exists, and import the vault-supplied access key
# (or generate one and print it for the vault).
#
# Run on the host after `make deploy-feederhub` brings the stack up
# (the garage service only starts once vault_feederhub_garage_rpc_secret
# is set).  Re-running is safe — every step is gated on current state.
#
# No CORS step, unlike the kizuna bootstrap: the browser never talks
# to this Garage. The feederhub server proxies photo uploads and
# serving, and the bucket stays private.
#
# Variables (set via env before running, or rely on the defaults):
#   FEEDERHUB_GARAGE_CONTAINER   default: feederhub-garage
#   FEEDERHUB_S3_BUCKET          default: feederhub
#   FEEDERHUB_S3_KEY_NAME        default: feederhub-app
#   FEEDERHUB_S3_ACCESS_KEY_ID   if set, import this key; if empty, a
#                                new one is generated and printed
#   FEEDERHUB_S3_SECRET_ACCESS_KEY  paired secret for import

set -euo pipefail

CONTAINER="${FEEDERHUB_GARAGE_CONTAINER:-feederhub-garage}"
BUCKET="${FEEDERHUB_S3_BUCKET:-feederhub}"
KEY_NAME="${FEEDERHUB_S3_KEY_NAME:-feederhub-app}"

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
# is applied; single-node deploys still need this.
if ! g status | grep -q '==== HEALTHY NODES ===='; then
  echo "Cluster status unreadable — aborting." >&2
  g status >&2 || true
  exit 1
fi

# `layout show` prints "No nodes currently have a role" until a layout
# is applied; gating on that string makes assign-then-apply idempotent.
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

# Step 3 — access key: import the vault pair, or generate + print one
# so it can be added to the vault (as vault_feederhub_s3_access_key_id
# / vault_feederhub_s3_secret_access_key) and this script re-run.
if [ -n "${FEEDERHUB_S3_ACCESS_KEY_ID:-}" ] && [ -n "${FEEDERHUB_S3_SECRET_ACCESS_KEY:-}" ]; then
  if g key info "${FEEDERHUB_S3_ACCESS_KEY_ID}" >/dev/null 2>&1; then
    echo "Key ${FEEDERHUB_S3_ACCESS_KEY_ID} already imported — skipping."
  else
    echo "Importing access key ${FEEDERHUB_S3_ACCESS_KEY_ID}..."
    g key import --yes \
      --name "${KEY_NAME}" \
      "${FEEDERHUB_S3_ACCESS_KEY_ID}" \
      "${FEEDERHUB_S3_SECRET_ACCESS_KEY}"
  fi
  ACCESS_KEY_ID="${FEEDERHUB_S3_ACCESS_KEY_ID}"
else
  if g key info "${KEY_NAME}" >/dev/null 2>&1; then
    echo "Key ${KEY_NAME} already exists — re-printing for the vault:"
    g key info --show-secret "${KEY_NAME}"
  else
    echo "No access key provided — generating ${KEY_NAME}..."
    g key create "${KEY_NAME}"
    echo
    echo "Add these to the vault as vault_feederhub_s3_access_key_id /"
    echo "vault_feederhub_s3_secret_access_key, then redeploy feederhub:"
    g key info --show-secret "${KEY_NAME}"
  fi
  ACCESS_KEY_ID="$(g key info "${KEY_NAME}" | awk '/Key ID:/ {print $3}')"
fi

# Step 4 — grant the key full access on the bucket.  `allow` is
# additive and idempotent.
echo "Granting ${ACCESS_KEY_ID} read+write+owner on ${BUCKET}..."
g bucket allow --read --write --owner "${BUCKET}" --key "${ACCESS_KEY_ID}"

echo "feederhub Garage bootstrap done."
