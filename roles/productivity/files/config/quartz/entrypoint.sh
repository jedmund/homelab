#!/bin/sh
set -e

CONTENT_DIR="/quartz/content"
OUTPUT_DIR="/usr/share/nginx/html"

# Clone content repo
if [ -n "$GIT_REPO" ]; then
  rm -rf "$CONTENT_DIR"
  git clone --branch "${GIT_BRANCH:-main}" --depth 1 "$GIT_REPO" "$CONTENT_DIR"
fi

# Initial build
cd /quartz
npx quartz build --output "$OUTPUT_DIR"

# Start nginx
nginx

# Auto rebuild loop
if [ "$AUTO_REBUILD" = "true" ]; then
  while true; do
    sleep "${BUILD_UPDATE_DELAY:-300}"
    cd "$CONTENT_DIR" && git pull --ff-only || true
    cd /quartz && npx quartz build --output "$OUTPUT_DIR" || true
  done
else
  tail -f /dev/null
fi
