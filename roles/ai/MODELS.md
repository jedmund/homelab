# Models

Reference for the GGUFs installed on `max` under `/opt/docker/ai/models/` and
served by `llama-swap` (chat / reranking) and TEI (embeddings). The `ai_models`
list in `roles/ai/defaults/main.yml` references each file by name; keep this
document and that list in sync when adding or removing a model.

Hardware budget: single NVIDIA RTX Pro 6000 Blackwell, 96 GB VRAM. Sizes below
are rough on-disk numbers for the quant chosen; live VRAM is usually a bit
higher once KV cache is allocated.

## Installed models

### qwen3.6-flash — daily driver, fastest

- **File**: `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`
- **Source**: `unsloth/Qwen3.6-35B-A3B-GGUF`
- **Pull**: `hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*UD-Q4_K_XL*.gguf" --local-dir .`
- **Why**: Qwen3.6 MoE (35B total, 3B active per token). ~240 tok/s on Blackwell,
  multimodal. Default chat model when latency matters more than depth.
- **VRAM**: ~22 GB on disk; ~26 GB live at 32k context.
- **Notes**: Non-MTP build on purpose. MTP barely helps MoE models (~1.15x) and
  costs ~1 GB VRAM, so the dense 27B below gets the MTP variant instead.

### qwen3.6 — daily driver, quality

- **File**: `Qwen3.6-27B-UD-Q4_K_XL.gguf` (unsloth puts the "MTP" marker on
  the repo, not the filename; this file is still the MTP build)
- **Source**: `unsloth/Qwen3.6-27B-MTP-GGUF`
- **Pull**: `hf download unsloth/Qwen3.6-27B-MTP-GGUF --include "*UD-Q4_K_XL*.gguf" --local-dir .`
- **Why**: Dense Qwen3.6 with multi-token prediction. ~160 tok/s on Blackwell,
  multimodal, 256K context. Use when the MoE flash model's answers feel thin.
- **VRAM**: ~17 GB on disk; ~22 GB live at 32k context.
- **Notes**: Needs `--spec-type draft-mtp`, which requires llama.cpp from
  2026-05-16 or newer. Pre-pull `ghcr.io/mostlygeek/llama-swap:cuda` before
  first deploy; if model fails to load with a flag error in `docker logs
  llama-swap`, the image is stale.

### gemma4 — different lineage from Qwen

- **File**: `gemma-4-31B-it-UD-Q4_K_XL.gguf`
- **Source**: `unsloth/gemma-4-31B-it-GGUF`
- **Pull**: `hf download unsloth/gemma-4-31B-it-GGUF --include "*UD-Q4_K_XL*.gguf" --local-dir .`
- **Why**: Google's top-of-Arena open dense model. Multimodal (text + image),
  256K context. Kept around to have a non-Qwen-family option when comparing
  answers or hitting Qwen-specific quirks.
- **VRAM**: ~19 GB on disk; ~24 GB live at 32k context.
- **Notes**: Sampling uses Google's recommended values (`--top-k 64`). No MTP
  variant available upstream.

### qwen3-coder — coding specialist

- **File**: `Qwen3-Coder-30B-A3B-Instruct-Q6_K.gguf`
- **Source**: `bartowski/Qwen3-Coder-30B-A3B-Instruct-GGUF`
- **Pull**: `hf download bartowski/Qwen3-Coder-30B-A3B-Instruct-GGUF --include "*Q6_K*.gguf" --local-dir .`
- **Why**: Coding-tuned MoE, still strong on diff / patch / tool-use tasks.
- **VRAM**: ~25 GB on disk; ~28 GB live at 16k context.
- **Notes**: Likely subsumed by Qwen3.6 eventually; keep until then.

### gpt-oss — different-lineage check against Qwen/Gemma

- **File**: `gpt-oss-120b-UD-Q4_K_XL-00001-of-00002.gguf` (+ remaining shards
  in the same directory; verify the actual shard count after download)
- **Source**: `unsloth/gpt-oss-120b-GGUF`
- **Pull**: `hf download unsloth/gpt-oss-120b-GGUF --include "*UD-Q4_K_XL*.gguf" --local-dir .`
- **Why**: OpenAI's open-weight 120B MoE (~5.1B active per token). Kept as a
  third lineage (alongside Qwen and Gemma) for genuine cross-family
  comparison; on 96 GB VRAM the 120B is the right tier, the 20B variant we
  used to run was sized for the previous 2x 3090 setup.
- **VRAM**: ~65-70 GB on disk; comfortably under the 96 GB ceiling at 32k
  context with KV quantisation.
- **Notes**: Split GGUF (same convention as MiniMax). `--jinja` for the
  chat template.

### minimax-m27 — big-brain for hard problems

- **File**: `MiniMax-M2.7-UD-IQ3_S-00001-of-00003.gguf` (+ shards 2 and 3 in
  the same directory)
- **Source**: `unsloth/MiniMax-M2.7-GGUF`
- **Pull**: `hf download unsloth/MiniMax-M2.7-GGUF --include "*UD-IQ3_S*.gguf" --local-dir .`
- **Why**: 229B / 10B-active MoE. Reserved for problems where the smaller
  models stall (long reasoning chains, hard refactors, tool-call planning).
- **VRAM**: ~78 GB on disk across three shards; close to the 96 GB ceiling
  live at 65k context.
- **Notes**: Split GGUF — too large for HuggingFace's per-file limit, so
  unsloth ships it as `*-00001-of-00003.gguf` ... `*-00003-of-00003.gguf`.
  llama.cpp handles this natively: point `--model` at shard 1 and it
  auto-loads the rest from the same directory. Pinned to flash-attn + q8_0
  KV quantisation to fit. `--jinja` is required for the chat template and
  tool-call handling to work. Sampling values pinned per MiniMax's
  recommendations.

### bge-reranker — RAG reranker

- **File**: `bge-reranker-v2-m3-Q8_0.gguf`
- **Source**: `gpustack/bge-reranker-v2-m3-GGUF`
- **Pull**: `hf download gpustack/bge-reranker-v2-m3-GGUF --include "*Q8_0*.gguf" --local-dir .`
- **Why**: Reranks retrieval hits for OpenWebUI's RAG. Low volume, so it stays
  in llama-swap rather than getting its own container.
- **VRAM**: ~600 MB. Short TTL (300s) so it unloads quickly between bursts.

## Speech-to-text (whisper / speaches, not llama-swap)

Voice input is served by the `whisper` container (speaches), not llama-swap.
The model lives in the `whisper-cache` named volume. Unlike TEI, speaches
does **not** lazy-download on first transcription — without a pre-pull,
the first request 404s with "Model '...' is not installed locally" and
OpenWebUI shows "Server Connection Error". The `Pre-pull whisper default
model` task in `tasks/main.yml` handles this idempotently on every deploy
(it skips the POST if the model is already in the cache).

- **Current model**: `Systran/faster-distil-whisper-large-v3` (pinned in
  `whisper_default_model` in `defaults/main.yml`). Distil variant is ~6x
  faster than `large-v3` for ~1% WER loss; good default for composer voice
  input. Switch to `Systran/faster-whisper-large-v3` for max accuracy on
  long-form transcription.
- **Manual pull** (if needed, e.g. after wiping the volume or adding a
  second model): `curl -X POST http://192.168.1.100:9000/v1/models/<id>`
  where `<id>` is a path from `GET /v1/registry?task=automatic-speech-recognition`.

## Embeddings (TEI, not llama-swap)

Embeddings are served by the TEI container, not llama-swap, so there is no
GGUF to manage on disk. TEI downloads its model on first start via the
HuggingFace hub and caches it in the `tei-cache` named volume.

- **Current model**: `nomic-ai/nomic-embed-text-v1.5` (pinned in
  `tei_model_id` in `defaults/main.yml`). Matches the model the retired
  llama-swap `nomic-embed` entry used to serve, so OpenWebUI and any other
  consumer swap in place without re-embedding.
- **Swap candidates**: `BAAI/bge-large-en-v1.5` or `Qwen/Qwen3-Embedding-8B`
  for top-of-MTEB at higher cost. Changing the model is not free for existing
  consumers: collections embedded with one model cannot be searched with
  another, so plan a re-embed (OpenWebUI: Admin -> Documents -> reset vector
  storage and re-ingest).

## Adding or removing a model

1. Download (or delete) the GGUF in `/opt/docker/ai/models/` on `max`. The
   filename must match exactly what you put in `ai_models`.
2. Edit `roles/ai/defaults/main.yml`:
   - Add or remove an entry in the `ai_models` list. Mirror the shape of the
     existing entries (`name`, `file`, `args`, optional `ttl`, `aliases`).
   - Use `aliases` to expose friendly names (`qwen3.6:35b-a3b`,
     `gpt-oss:20b`, etc.) that OpenWebUI and Ollama clients reach for.
3. Update this file to keep the catalogue + rationale honest.
4. Re-run `ansible-playbook deploy/ai.yml`. The llama-swap config template
   re-renders and the handler recreates the stack; llama-swap reloads its
   config on container restart.
5. Smoke-test from OpenWebUI (or directly):
   `curl -s http://192.168.1.100:11434/v1/models | jq` should list every
   `name` and `alias` from `ai_models`.
