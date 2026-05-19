# ai

GPU-bound AI services on `max`. Four containers in one stack:

| Service | Container | Host port | OpenAI-compatible |
|---|---|---|---|
| llama-swap (+ llama.cpp) | `mostlygeek/llama-swap:cuda` | `11434` | yes (chat) |
| whisper STT (speaches) | `speaches-ai/speaches:latest-cuda` | `9000` | yes (`/v1/audio/transcriptions`) |
| kokoro TTS | `remsky/kokoro-fastapi-gpu` | `8880` | yes (`/v1/audio/speech`) |
| TEI embeddings | `huggingface/text-embeddings-inference:cuda-latest` | `11435` | yes (`/v1/embeddings`) |
| SearXNG | `searxng/searxng` | `8889` | n/a (HTML/JSON search) |

OpenWebUI (running on `nuc-mini`) is wired to all four via env vars in
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

## Model files

Models are large binaries and live outside Ansible. Download them into
`{{ docker_base_path }}/ai/models/` on `max` so the container sees them at
`/models/`. The role's `ai_models` list in `defaults/main.yml` references each
file by name; update both the list and the directory in lockstep.

Current catalogue:

```bash
# Daily drivers — Qwen3.6 (multimodal, hybrid Gated DeltaNet + attention).
# The MTP variant of the dense 27B gets the real speedup; the MoE 35B-A3B
# uses the non-MTP build because MTP barely helps MoE models.
hf download unsloth/Qwen3.6-35B-A3B-GGUF     --include "*UD-Q4_K_XL*.gguf" --local-dir .
hf download unsloth/Qwen3.6-27B-MTP-GGUF     --include "*UD-Q4_K_XL*.gguf" --local-dir .

# Gemma 4 31B-it — Google's top-of-Arena open dense model
hf download unsloth/gemma-4-31B-it-GGUF      --include "*UD-Q4_K_XL*.gguf" --local-dir .

# Coding specialist (Qwen3.6 may eventually subsume this; keep for now)
hf download bartowski/Qwen3-Coder-30B-A3B-Instruct-GGUF --include "*Q6_K*.gguf" --local-dir .

# gpt-oss
hf download bartowski/openai_gpt-oss-20b-GGUF --include "*Q6_K*.gguf" --local-dir .

# MiniMax M2.7 — 229B/10B-active MoE, big-brain for hard problems
hf download unsloth/MiniMax-M2.7-GGUF --include "*UD-IQ3_S*.gguf" --local-dir .

# Reranker (for OpenWebUI semantic-search reranking)
hf download gpustack/bge-reranker-v2-m3-GGUF --include "*Q8_0*.gguf" --local-dir .
```

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
