#!/usr/bin/env bash

set -euo pipefail

files_root="/Volumes/Files"
apply_changes=false

usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [--files-root PATH] [--apply]" \
    "" \
    "Reorganize Files/models into HuggingHack's owner/repository layout." \
    "The default is a dry run; no files move unless --apply is supplied." \
    "" \
    "Options:" \
    "  --files-root PATH  Mounted root of the UniFi Files share" \
    "                     (default: /Volumes/Files)" \
    "  --apply            Perform the planned moves" \
    "  -h, --help         Show this help"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --files-root)
      [ "$#" -ge 2 ] || die "--files-root requires a path"
      files_root=$2
      shift 2
      ;;
    --apply)
      apply_changes=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $1"
      ;;
  esac
done

[ -d "$files_root" ] || die "Files share is not mounted at: $files_root"
files_root=$(cd "$files_root" && pwd -P)

source_root="$files_root/models"
destination_root="$files_root/HuggingHack"

[ -d "$source_root" ] || die "source model directory does not exist: $source_root"

# Each entry is relative to Files/models|relative to Files/HuggingHack.
# Keep the destination at exactly owner/repository so HuggingHack can derive
# the canonical Hugging Face repository ID.
mappings=(
  "DeepSeek-OCR|deepseek-ai/DeepSeek-OCR"
  "DeepSeek-V4-Flash-NVFP4|nvidia/DeepSeek-V4-Flash-NVFP4"
  "GLM-5.2/full|zai-org/GLM-5.2"
  "GLM-5.2/Q4_K_M/UD-Q4_K_M|unsloth/GLM-5.2-GGUF"
  "GLM-5.2-BF16-AMDMXFP4experts|festr2/GLM-5.2-BF16-AMDMXFP4experts"
  "GLM-5.2-NVFP4|lukealonso/GLM-5.2-NVFP4"
  "Inkling-NVFP4|thinkingmachines/Inkling-NVFP4"
  "Kimi-K2.7-Code|moonshotai/Kimi-K2.7-Code"
  "Kimi-K2.7-Code-NVFP4|nvidia/Kimi-K2.7-Code-NVFP4"
  "Kokoro-82M|hexgrad/Kokoro-82M"
  "Laguna-S-2.1-NVFP4|poolside/Laguna-S-2.1-NVFP4"
  "MiMo-V2.5-NVFP4|lukealonso/MiMo-V2.5-NVFP4"
  "MiMo-V2.5-Pro-FP4-DFlash|XiaomiMiMo/MiMo-V2.5-Pro-FP4-DFlash"
  "MiniMax-M3-MXFP8|MiniMaxAI/MiniMax-M3-MXFP8"
  "MiniMax-M3-NVFP4|nvidia/MiniMax-M3-NVFP4"
  "PaddleOCR-VL|PaddlePaddle/PaddleOCR-VL"
  "Qwen3-Embedding-4B|Qwen/Qwen3-Embedding-4B"
  "Qwen3-Embedding-8B|Qwen/Qwen3-Embedding-8B"
  "Qwen3-Reranker-4B|Qwen/Qwen3-Reranker-4B"
  "Qwen3-Reranker-8B|Qwen/Qwen3-Reranker-8B"
  "Qwen3-VL-30B-A3B-Instruct|Qwen/Qwen3-VL-30B-A3B-Instruct"
  "Qwen3-VL-32B-Instruct|Qwen/Qwen3-VL-32B-Instruct"
  "Qwen3-VL-8B-Instruct|Qwen/Qwen3-VL-8B-Instruct"
  "Qwen3.6-27B-NVFP4|nvidia/Qwen3.6-27B-NVFP4"
  "Qwen3.6-35B-A3B-NVFP4|nvidia/Qwen3.6-35B-A3B-NVFP4"
  "dots.ocr|dots-studio/dots.ocr"
  "parakeet-tdt-0.6b-v3|nvidia/parakeet-tdt-0.6b-v3"
  "speaker-diarization-community-1|pyannote/speaker-diarization-community-1"
)

planned=0
already_migrated=0
missing=0
conflicts=0

printf 'HuggingHack model migration\n'
printf '  Source:      %s\n' "$source_root"
printf '  Destination: %s\n\n' "$destination_root"

for mapping in "${mappings[@]}"; do
  source_relative=${mapping%%|*}
  destination_relative=${mapping#*|}
  source_path="$source_root/$source_relative"
  destination_path="$destination_root/$destination_relative"

  if path_exists "$source_path" && path_exists "$destination_path"; then
    printf 'CONFLICT  %s\n          destination already exists: %s\n' \
      "$source_relative" "$destination_relative"
    conflicts=$((conflicts + 1))
  elif path_exists "$source_path"; then
    [ -d "$source_path" ] || die "expected a directory: $source_path"
    printf 'MOVE      %s -> %s\n' "$source_relative" "$destination_relative"
    planned=$((planned + 1))
  elif path_exists "$destination_path"; then
    [ -d "$destination_path" ] || die "expected a directory: $destination_path"
    printf 'DONE      %s\n' "$destination_relative"
    already_migrated=$((already_migrated + 1))
  else
    printf 'MISSING   %s\n' "$source_relative"
    missing=$((missing + 1))
  fi
done

printf '\nSummary: %d to move, %d already moved, %d missing, %d conflicts\n' \
  "$planned" "$already_migrated" "$missing" "$conflicts"

[ "$conflicts" -eq 0 ] || die "resolve conflicts before applying; nothing was moved"

if ! $apply_changes; then
  printf '\nDry run only. Re-run with --apply to perform these moves.\n'
  exit 0
fi

[ "$planned" -gt 0 ] || {
  printf '\nNothing to move.\n'
  exit 0
}

# Check every source and the nearest existing destination parent before making
# any changes. A rerun remains safe if the share disconnects mid-migration.
for mapping in "${mappings[@]}"; do
  source_relative=${mapping%%|*}
  destination_relative=${mapping#*|}
  source_path="$source_root/$source_relative"
  destination_path="$destination_root/$destination_relative"

  path_exists "$source_path" || continue

  source_parent=${source_path%/*}
  [ -w "$source_parent" ] ||
    die "source parent is not writable: $source_parent"

  destination_parent=${destination_path%/*}
  while [ ! -d "$destination_parent" ]; do
    next_parent=${destination_parent%/*}
    [ "$next_parent" != "$destination_parent" ] ||
      die "could not find an existing parent for: $destination_path"
    destination_parent=$next_parent
  done
  [ -w "$destination_parent" ] ||
    die "destination parent is not writable: $destination_parent"
done

if [ -d "$destination_root" ]; then
  [ -w "$destination_root" ] ||
    die "destination is not writable: $destination_root"
else
  [ -w "$files_root" ] || die "Files share is not writable: $files_root"
  mkdir -p "$destination_root"
fi

printf '\nApplying migration...\n'

for mapping in "${mappings[@]}"; do
  source_relative=${mapping%%|*}
  destination_relative=${mapping#*|}
  source_path="$source_root/$source_relative"
  destination_path="$destination_root/$destination_relative"

  path_exists "$source_path" || continue
  path_exists "$destination_path" &&
    die "destination appeared during migration: $destination_path"

  mkdir -p "${destination_path%/*}"
  mv "$source_path" "$destination_path"
  printf 'MOVED     %s -> %s\n' "$source_relative" "$destination_relative"
done

printf '\nMigration complete. Empty source directories were intentionally left in place.\n'
printf 'Deploy HuggingHack, then use Local Library -> Scan storage.\n'
