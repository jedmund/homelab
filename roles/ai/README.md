# ai

llama-swap on `max`, fronting llama.cpp. Hot-swaps models on demand; exposes an
OpenAI-compatible API (port `11434`, the Ollama port — OpenWebUI on `nuc-mini`
talks to it as an OpenAI endpoint).

## Layout

```
{{ docker_base_path }}/ai/
├── compose.yaml                # rendered from templates/compose.yaml.j2
├── config/
│   └── llama-swap.yaml         # rendered from templates/config/llama-swap.yaml.j2
└── models/                     # GGUF files, populated out of band
```

## Model files

Models are large binaries and live outside Ansible. Download them into
`{{ docker_base_path }}/ai/models/` on `max` so the container sees them at
`/models/`. The role's `ai_models` list in `defaults/main.yml` references each
file by name; update both the list and the directory in lockstep.

Current catalogue (matches the prototype stack at `/opt/stacks/ai/`):

```bash
# Daily-driver Qwen3 family
hf download bartowski/Qwen3-14B-GGUF       --include "*q6_k*.gguf"     --local-dir .
hf download bartowski/Qwen_Qwen3-32B-GGUF  --include "*Q4_K_M*.gguf"   --local-dir .
hf download bartowski/Qwen3-Coder-30B-A3B-Instruct-GGUF --include "*Q6_K*.gguf" --local-dir .

# gpt-oss
hf download bartowski/openai_gpt-oss-20b-GGUF --include "*Q6_K*.gguf"  --local-dir .

# Vision (needs both the model and the mmproj projection)
hf download bartowski/Qwen3VL-8B-Instruct-GGUF --include "*Q8_0*.gguf"          --local-dir .
hf download bartowski/Qwen3VL-8B-Instruct-GGUF --include "mmproj-*F16*.gguf"    --local-dir .

# MiniMax M2.7 — 229B/10B-active MoE, agentic + coding
hf download unsloth/MiniMax-M2.7-GGUF --include "*UD-IQ3_S*.gguf" --local-dir .

# Embeddings + reranker (for OpenWebUI semantic search)
hf download nomic-ai/nomic-embed-text-v1.5-GGUF --include "*Q8_0*.gguf" --local-dir .
hf download gpustack/bge-reranker-v2-m3-GGUF    --include "*Q8_0*.gguf" --local-dir .
```

## Hardware notes

The current target is `max` (single NVIDIA RTX Pro 6000 Blackwell, 96 GB
VRAM). The compose service uses `deploy.resources.reservations.devices` with
`driver: nvidia, count: all`, so any GPU set the host exposes via the NVIDIA
container toolkit is picked up automatically.

The MiniMax M2.7 entry pins flash-attn, q8_0 KV quantisation, and MiniMax's
recommended sampling params. Without `--jinja` the chat template and
tool-calling break.
