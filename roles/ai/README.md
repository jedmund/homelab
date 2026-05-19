# ai

GPU-bound AI services on `max`. Five containers in one stack:

| Service | Container | Host port | OpenAI-compatible |
|---|---|---|---|
| llama-swap (+ llama.cpp) | `mostlygeek/llama-swap:cuda` | `11434` | yes (chat) |
| whisper STT (speaches) | `speaches-ai/speaches:latest-cuda` | `9000` | yes (`/v1/audio/transcriptions`) |
| kokoro TTS | `remsky/kokoro-fastapi-gpu` | `8880` | yes (`/v1/audio/speech`) |
| TEI embeddings | `huggingface/text-embeddings-inference:cuda-latest` | `11435` | yes (`/v1/embeddings`) |
| SearXNG | `searxng/searxng` | `8889` | n/a (HTML/JSON search) |

OpenWebUI (running on `nuc-mini`) is wired to all of these via env vars in
`roles/development`; nothing needs to be set in the OpenWebUI admin UI
after deployment.

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

Embeddings are served by TEI, not llama-swap; TEI downloads its model
(`nomic-ai/nomic-embed-text-v1.5`) on first start via the HF hub.

## Hardware notes

The current target is `max` (single NVIDIA RTX Pro 6000 Blackwell, 96 GB
VRAM). The compose service uses `deploy.resources.reservations.devices` with
`driver: nvidia, count: all`, so any GPU set the host exposes via the NVIDIA
container toolkit is picked up automatically.

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
