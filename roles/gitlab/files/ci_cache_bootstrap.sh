#!/usr/bin/env bash
#
# ci_cache_bootstrap.sh - one-time + re-runnable Garage setup for the GitLab
# CI runner cache. Applies a cluster layout, ensures the ci-cache bucket
# exists, and imports the vault-supplied access key (or generates + prints a
# new one if the vault entries are empty so they can be added).
#
# Run this on nuc-mini after `make deploy-gitlab` brings the stack up.
# Re-running is safe - every step is gated on current state.
#
# Variables (set via env before running, or edit defaults below):
#   CI_CACHE_GARAGE_CONTAINER  default: gitlab-cache-garage
#   CI_CACHE_S3_BUCKET         default: ci-cache
#   CI_CACHE_S3_ACCESS_KEY_ID  if set, import this key; if empty, a new one
#                              is generated and printed for the vault
#   CI_CACHE_S3_SECRET_ACCESS_KEY  paired secret for import
#
# Unlike the kizuna bootstrap this sets no CORS: the cache is server-to-server
# runner traffic only, never a browser origin.

set -euo pipefail

CONTAINER="${CI_CACHE_GARAGE_CONTAINER:-gitlab-cache-garage}"
BUCKET="${CI_CACHE_S3_BUCKET:-ci-cache}"
KEY_NAME="${CI_CACHE_S3_KEY_NAME:-ci-cache-key}"
EXPIRY_DAYS="${CI_CACHE_S3_EXPIRY_DAYS:-14}"
CIBUILD_NETWORK="${CI_CACHE_CIBUILD_NETWORK:-cibuild-network}"
MC_IMAGE="${CI_CACHE_MC_IMAGE:-minio/mc}"

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

# Step 1 - cluster layout. Garage refuses S3 traffic until a layout is
# applied; single-node deploys still need this. Gate on the exact string
# `layout show` prints when no role has ever been assigned, so re-runs no-op.
if ! g status | grep -q '==== HEALTHY NODES ===='; then
  echo "Cluster status unreadable - aborting." >&2
  g status >&2 || true
  exit 1
fi

if g layout show 2>&1 | grep -q 'No nodes currently have a role'; then
  NODE_ID="$(g node id -q | cut -d@ -f1)"
  echo "Assigning layout to node ${NODE_ID}..."
  g layout assign -z dc1 -c 1G "${NODE_ID}"
  g layout apply --version 1
else
  echo "Layout already applied - skipping."
fi

# Step 2 - bucket.
if g bucket info "${BUCKET}" >/dev/null 2>&1; then
  echo "Bucket ${BUCKET} exists - skipping create."
else
  echo "Creating bucket ${BUCKET}..."
  g bucket create "${BUCKET}"
fi

# Step 3 - access key. Import the vault-supplied key if present, otherwise
# generate one and print it so the operator can add it to the vault and
# re-run with the env vars set.
if [ -n "${CI_CACHE_S3_ACCESS_KEY_ID:-}" ] && [ -n "${CI_CACHE_S3_SECRET_ACCESS_KEY:-}" ]; then
  if g key info "${CI_CACHE_S3_ACCESS_KEY_ID}" >/dev/null 2>&1; then
    echo "Key ${CI_CACHE_S3_ACCESS_KEY_ID} already imported - skipping."
  else
    echo "Importing access key ${CI_CACHE_S3_ACCESS_KEY_ID}..."
    g key import --yes \
      --name "${KEY_NAME}" \
      "${CI_CACHE_S3_ACCESS_KEY_ID}" \
      "${CI_CACHE_S3_SECRET_ACCESS_KEY}"
  fi
else
  if g key info "${KEY_NAME}" >/dev/null 2>&1; then
    echo "Key ${KEY_NAME} already exists - re-printing for the vault:"
    g key info --show-secret "${KEY_NAME}"
  else
    echo "No access key provided - generating ${KEY_NAME}..."
    g key create "${KEY_NAME}"
    echo
    echo "Add these to group_vars/compute_servers/vault.yml, then re-run:"
    echo "  gitlab_cache_s3_access_key_id / gitlab_cache_s3_secret_access_key"
    g key info --show-secret "${KEY_NAME}"
    exit 0
  fi
fi

# Step 4 - grant the key full access on the bucket. `allow` is additive and
# idempotent; the Ansible deploy re-applies this on every run too.
ACCESS_KEY_ID="${CI_CACHE_S3_ACCESS_KEY_ID:-$(g key info "${KEY_NAME}" | awk '/Key ID:/ {print $3}')}"
echo "Granting ${ACCESS_KEY_ID} read+write+owner on ${BUCKET}..."
g bucket allow --read --write --owner "${BUCKET}" --key "${ACCESS_KEY_ID}"

# Step 5 - object-expiry lifecycle. GitLab never prunes its own cache objects,
# so a native Garage S3 lifecycle rule expires them after EXPIRY_DAYS. `ilm
# import` replaces the whole lifecycle config, so re-running is idempotent.
# Garage's CLI has no lifecycle command, hence the one-shot mc client. The
# Ansible deploy applies the same rule on every run.
SECRET_KEY="${CI_CACHE_S3_SECRET_ACCESS_KEY:-$(g key info --show-secret "${ACCESS_KEY_ID}" | awk '/Secret key:/ {print $3}')}"
echo "Setting ${EXPIRY_DAYS}d object-expiry lifecycle on ${BUCKET}..."
printf '%s' "{\"Rules\":[{\"ID\":\"expire-ci-cache\",\"Status\":\"Enabled\",\"Filter\":{\"Prefix\":\"\"},\"Expiration\":{\"Days\":${EXPIRY_DAYS}},\"AbortIncompleteMultipartUpload\":{\"DaysAfterInitiation\":1}}]}" \
  | docker run --rm -i --network "${CIBUILD_NETWORK}" \
      -e MC_HOST_cache="http://${ACCESS_KEY_ID}:${SECRET_KEY}@${CONTAINER}:3900" \
      "${MC_IMAGE}" ilm import "cache/${BUCKET}"

echo "CI cache Garage bootstrap done."
