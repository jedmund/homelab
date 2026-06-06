# ai

GPU-bound AI services on `max`. Seven containers in one stack:

| Service | Container | Host port | OpenAI-compatible |
|---|---|---|---|
| llama-swap (+ llama.cpp) | `mostlygeek/llama-swap:cuda` | `11434` | yes (chat, embeddings in `embed` group) |
| whisper STT (speaches) | `speaches-ai/speaches:latest-cuda` | `9000` | yes (`/v1/audio/transcriptions`) |
| kokoro TTS | `remsky/kokoro-fastapi-gpu` | `8880` | yes (`/v1/audio/speech`) |
| TEI embeddings (Qwen3) | `huggingface/text-embeddings-inference:cuda-latest` | `11435` | yes (`/v1/embeddings`) |
| TEI embeddings (jina-v3) | `huggingface/text-embeddings-inference:cuda-latest` | `11436` | yes (`/v1/embeddings`) |
| SearXNG | `searxng/searxng` | `8889` | n/a (HTML/JSON search) |
| Playwright | `mcr.microsoft.com/playwright` | `3000` | n/a (WebSocket only) |

OpenWebUI (running on `nuc-mini`) is wired to all of these via env vars in
`roles/open_webui`. Most env vars take effect on first deploy only —
OpenWebUI persists them to its database and subsequent restarts use the
DB value, so changing an env var on an existing install requires either
editing it in Admin -> Settings or a one-shot start with
`RESET_CONFIG_ON_START=true`.

The Playwright sidecar exists because OpenWebUI's default web loader is
LangChain's httpx-based `WebBaseLoader`, which most modern sites block;
without Playwright, web search "succeeds" but every page fetch returns
0 bytes and the chat reports "No sources found". The image tag is
pinned to match the `playwright==X.Y.Z` line in OpenWebUI's
`backend/requirements.txt` — bump `playwright_version` (and the image
tag in `playwright_image`) together when OpenWebUI updates Playwright.

## Layout

```
{{ docker_base_path }}/ai/
├── compose.yaml                # rendered from templates/compose.yaml.j2
├── config/
│   ├── llama-swap.yaml         # rendered from templates/config/llama-swap.yaml.j2
│   └── searxng/settings.yml    # rendered from templates/config/searxng/settings.yml.j2
└── models/                     # GGUF files, populated out of band
```

## Secrets in vault

- `searxng_secret_key` — generate with `openssl rand -hex 32`. SearXNG
  refuses to start with the empty default.

## Models

The model catalogue (what's installed, why, how to pull each GGUF, how to add
or swap one) lives in [MODELS.md](MODELS.md). The `ai_models` list in
`defaults/main.yml` is the source of truth for what llama-swap serves;
MODELS.md is the human-readable companion.

Embeddings split across two surfaces:

- **Always-on (TEI)** for OpenWebUI RAG and any other "no cold-load tax"
  consumer. Two containers, each pinned to one model:
  - `tei` -> `Qwen/Qwen3-Embedding-0.6B` at `:11435` (read from local
    snapshot at `models/Qwen3-Embedding-0.6B/`).
  - `tei-jina` -> `jinaai/jina-embeddings-v3` at `:11436` (read from local
    snapshot at `models/jina-embeddings-v3/`).
- **Swap-loaded (llama-swap)** for project experimentation. The `embed`
  group has `swap: true`, so only one of `bge-m3`, `qwen3-embed-0_6b`,
  `qwen3-embed-4b` is resident at a time, served at `:11434/v1/embeddings`.

## Hardware notes

The current target is `max` (two NVIDIA RTX Pro 6000 Blackwell cards: one
600 W Workstation + one 300 W Max-Q, 192 GB VRAM total). The compose
services use `deploy.resources.reservations.devices` with
`driver: nvidia, count: all`, so any GPU set the host exposes via the
NVIDIA container toolkit is picked up automatically.

## Llama.cpp version requirement

The `qwen3.6` (Qwen3.6-27B-MTP) entry uses the `--spec-type draft-mtp` flag,
which requires llama.cpp from 2026-05-16 or later. Before first deploy, run
`docker pull ghcr.io/mostlygeek/llama-swap:cuda` on `max` to ensure the
bundled llama-server is recent enough; if MTP-enabled models fail to start
with a flag error in `docker logs llama-swap`, the image is stale and a
pull will fix it.

The MiniMax M2.7 entry pins flash-attn, q8_0 KV quantisation, and MiniMax's
recommended sampling params. Without `--jinja` the chat template and
tool-calling break for it, Gemma 4, and Qwen3.6.

## First-time deploy

`docker compose up` on a fresh `max` has to pull roughly 20–30 GB of CUDA
images, and Ansible buffers task output until the module returns, so the
`Deploy ai stack` task can look frozen for many minutes. Pre-pull the images
(`docker pull` each one in `compose.yaml.j2`) before running the playbook for
the first time to avoid the perceived hang.
