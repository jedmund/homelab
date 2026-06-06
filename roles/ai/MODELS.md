# Models

Reference for the GGUFs installed on `max` under `/opt/docker/ai/models/` and
served by `llama-swap` (chat / reranking) and TEI (embeddings). The `ai_models`
list in `roles/ai/defaults/main.yml` references each file by name; keep this
document and that list in sync when adding or removing a model.

Hardware budget after the 2026-06-01 rebuild: 3x NVIDIA RTX Pro 6000
Blackwell, 288 GB VRAM total. Two are Max-Q Workstation Edition (300 W,
indices 0 and 1); one is full Workstation Edition (600 W, index 2). All
three are bandwidth-comparable enough that llama.cpp's default layer-split
works in shared mode without an explicit `--tensor-split`; if profiling
shows the 600 W card under-utilised, tune via `--tensor-split 1,1,1.1`.
Sizes below are rough on-disk numbers for the quant chosen; live VRAM is
usually a bit higher once KV cache is allocated.

## GPU allocation modes

llama-swap and SGLang share the same three cards via a deploy-time toggle.
The `ai_gpu_mode` variable in `roles/ai/defaults/main.yml` controls the
split:

| Mode | llama-swap GPUs | SGLang GPUs | When to pick |
|---|---|---|---|
| `split` (default) | index 2 (96 GB) | indices 0,1 via TP=2 (192 GB) | Concurrent DeepSeek + llama-swap. Smaller llama-swap catalogue (no minimax-q4 / gpt-oss / minimax-iq4). |
| `shared` | indices 0,1,2 (288 GB) | none (SGLang torn down) | Heavy llama-swap workloads needing the big models; DeepSeek is off. |

Switch via `make deploy-ai-split` or `make deploy-ai-shared`. Switching
restarts the llama-swap container (drops resident models; next request
pays the cold-load tax) and, in shared mode, runs `docker compose -p
sglang down` so the Max-Q pair isn't contended. SGLang model load on
V4 Flash is several minutes either way, so treat the toggle as a
deliberate mode change, not a hot swap.

## llama-swap usage modes (within a given GPU mode)

The catalog is organised around three usage modes via the `chat`, `code`,
and `code-heavy` llama-swap groups. In `ai_gpu_mode: shared` all three
modes are available; in `split` mode only the chat group is loadable
(the `code` and `code-heavy` entries are filtered out of the rendered
`llama-swap.yaml` via their `requires_mode: shared` flag).

| Usage mode | Active | Group occupancy | VRAM live | Available in |
|---|---|---|---|---|
| 1: solo coding | `minimax-m27-q4` or `gpt-oss` | `code-heavy` (exclusive: true) | ~185 GB / ~125 GB | shared |
| 2: coexistence | `minimax-m27-iq4` + a chat model | `code` + `chat` | ~135 GB + ~36-54 GB | shared |
| 3: chat alone | any chat model | `chat` only | ~36-75 GB | split + shared |

In split mode, only mode 3 is reachable (single 96 GB card). The two
chat models sized for coexistence with the code group still apply in
shared mode:

- `qwen3.6` (dense Q6 MTP) at `-c 131072 --parallel 2` -> ~36 GB live.
- `qwen3.6-flash` (Q8_K_XL MoE) at `-c 131072 --parallel 4` -> ~54 GB live.

The other chat-tier entries (`qwen3.6-flash-uncensored`, `gemma4`,
`gemma4-uncensored`, `gemma-e4b-uncensored`, `qwen3-coder`) keep their
larger contexts because they're picked manually; in shared mode loading
one while minimax-iq4 is resident may OOM (unload the code slot first).
`qwen3.6-flash-uncensored` is openclaw's default chat and vision model,
so in shared mode an openclaw DM will evict any resident code slot.
In split mode the chat group has the WS card to itself, so all of them
fit individually.

## Installed models

### qwen3.6-flash: daily driver, fastest

- **Files**:
  - Weights: `Qwen3.6-35B-A3B-UD-Q8_K_XL.gguf` (top-level)
  - mmproj: `Qwen3.6-35B-A3B/mmproj-F16.gguf` (per-model subdir; Unsloth
    publishes mmproj under a generic name so each one lives in its own
    subdirectory to avoid collisions)
- **Source**: `unsloth/Qwen3.6-35B-A3B-GGUF`
- **Pull**:
  - `hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "*UD-Q8_K_XL*.gguf" --local-dir .`
  - `hf download unsloth/Qwen3.6-35B-A3B-GGUF --include "mmproj*.gguf" --local-dir ./Qwen3.6-35B-A3B/`
- **Why**: Qwen3.6 MoE (35B total, 3B active per token). ~240 tok/s on
  Blackwell, multimodal. Bumped to Q8_K_XL once the second Blackwell
  arrived: MoE token decode reads only active params, so Q8 costs
  effectively nothing in throughput while giving a real weights-quality
  bump.
- **VRAM**: ~37 GB on disk; ~54 GB live with `--parallel 4 -c 131072`
  (four sticky 32K slots, q8_0 KV). Sized to fit alongside
  `minimax-m27-iq4` (~135 GB) in coexistence mode 2.
- **Notes**: Non-MTP build on purpose. MTP barely helps MoE models
  (~1.15x) and costs ~1 GB VRAM, so the dense 27B below gets the MTP
  variant instead. `--mmproj` wires up vision; without it text-only
  inference still works but image inputs are dropped.

### qwen3.6-flash-uncensored: abliterated variant of the MoE flash model

- **Files**:
  - Weights: `Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf`
  - mmproj: `mmproj-Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-f16.gguf` (~900 MB)
- **Source**: `HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive`
- **Pull**:
  - `hf download HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf --local-dir .`
  - `hf download HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive mmproj-Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-f16.gguf --local-dir .`
- **Why**: Abliterated (refusal-vector-removed) build of the same base
  model as `qwen3.6-flash`, kept at the same fidelity tier (~10 bpw) so
  quality comparisons against the non-abliterated sibling stay clean.
  Default openclaw chat and vision model: image-bearing DMs route here
  automatically via `agents.defaults.imageModel`, so text and image
  turns share the same refusal policy. Keep both flash entries resident
  in the catalogue so requests can pick per use case; `swap: true` means
  only one is in VRAM at a time, so the cost is disk-only (~44 GB).
- **VRAM**: ~44 GB on disk; ~75 GB live with `--parallel 4 -c 262144`
  (four sticky 64K slots, q8_0 KV). Same shape as `qwen3.6-flash`.
- **Notes**: "Q8_K_P" is HauhauCS's analog of Unsloth's UD-Q8_K_XL:
  selective higher-precision tensors on the layers that matter most.
  The "Aggressive" suffix means more thorough refusal removal than the
  standard abliterated variant; downside is that over-suppressed refusal
  vectors can leak into benign reasoning, so if coherence on normal
  tasks degrades, switch to a less aggressive HauhauCS build. mmproj is
  shipped as a separate file and now wired up via `--mmproj`; both
  weights and mmproj must be present before llama-server boots, or it
  fails to start.

### qwen3.6: daily driver, quality

- **Files**:
  - Weights: `Qwen3.6-27B-UD-Q6_K_XL.gguf` (top-level; unsloth puts the
    "MTP" marker on the repo, not the filename; this file is still the
    MTP build)
  - mmproj: `Qwen3.6-27B/mmproj-F16.gguf` (per-model subdir)
- **Source**: `unsloth/Qwen3.6-27B-MTP-GGUF`
- **Pull**:
  - `hf download unsloth/Qwen3.6-27B-MTP-GGUF --include "*UD-Q6_K_XL*.gguf" --local-dir .`
  - `hf download unsloth/Qwen3.6-27B-MTP-GGUF --include "mmproj*.gguf" --local-dir ./Qwen3.6-27B/`
- **Why**: Dense Qwen3.6 with multi-token prediction. ~160 tok/s at Q4 on
  Blackwell, multimodal. Bumped to Q6_K_XL once the second Blackwell
  arrived: for dense models token decode reads all weights, so the
  bigger quant costs ~20% throughput (~130 tok/s expected) but gives a
  meaningful quality bump. Q8 would halve throughput, too steep for
  this tier.
- **VRAM**: ~22 GB on disk; ~36 GB live with `--parallel 2 -c 131072`
  (two sticky 64K slots, q8_0 KV). Sized for coexistence with
  `minimax-m27-iq4` (~135 GB) in mode 2; total ~171 GB, ~18 GB headroom.
  Mode 3 leaves a lot of VRAM unused, but qwen3.6 stays at 128K total
  context; add a wider-context variant later if 64K-per-chat-session
  pinches.
- **Notes**: Needs `--spec-type draft-mtp`, which requires llama.cpp from
  2026-05-16 or newer. Pre-pull `ghcr.io/mostlygeek/llama-swap:cuda`
  before first deploy; if model fails to load with a flag error in
  `docker logs llama-swap`, the image is stale. `--mmproj` wires up
  vision; image inputs require the mmproj file to be present alongside
  the weights.

### gemma4: different lineage from Qwen

- **Files**:
  - Weights: `gemma-4-31B-it-UD-Q6_K_XL.gguf` (top-level)
  - mmproj: `gemma-4-31B-it/mmproj-F16.gguf` (per-model subdir)
- **Source**: `unsloth/gemma-4-31B-it-GGUF`
- **Pull**:
  - `hf download unsloth/gemma-4-31B-it-GGUF --include "*UD-Q6_K_XL*.gguf" --local-dir .`
  - `hf download unsloth/gemma-4-31B-it-GGUF --include "mmproj*.gguf" --local-dir ./gemma-4-31B-it/`
- **Why**: Google's top-of-Arena open dense model. Multimodal (text +
  image), 256K context. Kept around to have a non-Qwen-family option
  when comparing answers or hitting Qwen-specific quirks. Bumped to
  Q6_K_XL alongside qwen3.6 once the second Blackwell arrived; same
  reasoning (dense throughput cost is real, Q6 is the sweet spot).
- **VRAM**: ~25 GB on disk; ~55 GB live with `--parallel 4 -c 262144`
  (four sticky 64K slots, q8_0 KV).
- **Notes**: Sampling uses Google's recommended values (`--top-k 64`).
  No MTP variant available upstream. `--mmproj` wires up vision;
  Gemma 4's image input format follows the standard llama-server
  vision protocol.

### gemma4-uncensored: abliterated MoE Gemma 4

- **Files**:
  - Weights: `Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-Q8_K_P.gguf`
  - mmproj: `mmproj-Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-f16.gguf` (verify after download)
- **Source**: `HauhauCS/Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced`
- **Pull**:
  - `hf download HauhauCS/Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-Q8_K_P.gguf --local-dir .`
  - `hf download HauhauCS/Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced mmproj-Gemma4-26B-A4B-Uncensored-HauhauCS-Balanced-f16.gguf --local-dir .`
- **Why**: Abliterated MoE companion to the dense `gemma4` entry. 26B
  total / 4B active per token, so decode speed is closer to a 4B model
  than to the 31B dense flagship. "Balanced" abliteration removes
  refusals less aggressively than "Aggressive", which keeps benign-task
  coherence higher; the tradeoff is a few more residual refusals.
- **VRAM**: ~33 GB on disk; ~60 GB live with `--parallel 4 -c 262144`
  (four sticky 64K slots, q8_0 KV).
- **Notes**: Q8_K_P (~10 bpw) is HauhauCS's analog of Unsloth's
  UD-Q8_K_XL. MoE means the bigger quant is essentially free in tok/s.
  Sampling uses Gemma's recommended `--top-k 64`. `--mmproj` wires up
  vision; image inputs require the mmproj file to be present alongside
  the weights before llama-server boots.

### gemma-e4b-uncensored: small dense Gemma 4 (abliterated)

- **Files**:
  - Weights: `Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf`
  - mmproj: `mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf` (verify after download)
- **Source**: `HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive`
- **Pull**:
  - `hf download HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q8_K_P.gguf --local-dir .`
  - `hf download HauhauCS/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive mmproj-Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-f16.gguf --local-dir .`
- **Why**: Small dense Gemma 4 "E4B" variant for quick low-latency
  tasks; abliterated for cases where refusal training on a small model
  gets noisy. Sized similarly to `qwen3-small` but kept in the GPU
  `chat` group rather than the CPU `cpu` group because it's intended
  for interactive use, not compaction.
- **VRAM**: ~5 GB on disk; ~12 GB live with `--parallel 4 -c 131072`
  (four sticky 32K slots, q8_0 KV). Lower context budget than the
  rest of the chat group because a 4B model isn't typically reached
  for project-scale conversations.
- **Notes**: "Aggressive" abliteration removes refusal vectors more
  thoroughly; possible coherence leak on benign prompts. Swap for a
  Balanced HauhauCS build if that bites in practice. `--mmproj` wires
  up vision; image inputs require the mmproj file alongside the
  weights before llama-server boots.

### qwen3-coder: coding specialist

- **File**: `Qwen3-Coder-30B-A3B-Instruct-UD-Q8_K_XL.gguf`
- **Source**: `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF` (switched from
  bartowski to unsloth for consistency with the rest of the catalogue;
  if Unsloth doesn't publish a `UD-Q8_K_XL` for this model, fall back to
  bartowski's `Q8_0` and adjust the file/pull lines accordingly).
- **Pull**: `hf download unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF --include "*UD-Q8_K_XL*.gguf" --local-dir .`
- **Why**: Coding-tuned MoE (30B total, 3B active per token). Strong on
  diff / patch / tool-use tasks. Bumped from Q6 to Q8_K_XL alongside
  qwen3.6-flash: MoE decode reads only active params, so the bigger
  quant is essentially free in tok/s. Context bumped from 16K to four
  64K sticky slots: 16K was painful for any non-trivial coding session.
- **VRAM**: ~32 GB on disk; ~60 GB live with `--parallel 4 -c 262144`
  (four sticky 64K slots, q8_0 KV).
- **Notes**: Likely subsumed by Qwen3.6 eventually; keep until then.

### gpt-oss: different-lineage check against Qwen/Gemma

- **File**: `UD-Q6_K_XL/gpt-oss-120b-UD-Q6_K_XL-00001-of-00002.gguf`
  (organised under a per-quant subdirectory; verify the actual shard
  count after download and adjust the path if it differs).
- **Source**: `unsloth/gpt-oss-120b-GGUF`
- **Pull**: `hf download unsloth/gpt-oss-120b-GGUF --include "*UD-Q6_K_XL*.gguf" --local-dir ./UD-Q6_K_XL/`
- **Why**: OpenAI's open-weight 120B MoE (~5.1B active per token). The
  heavy reasoning alternative to `minimax-m27-q4` for cross-family
  comparison on hard problems. Lives in the `code-heavy` group
  (`exclusive: true`), so loading it evicts the chat group; pick it
  when you want max quality and accept that openclaw chat will need to
  cold-load when it's next called.
- **VRAM**: ~95 GB on disk; ~125 GB live with `--parallel 4 -c 131072`
  (four sticky 32K slots, q8_0 KV). Smaller live footprint than
  minimax-m27-q4 (~185 GB) so there's plenty of room to grow the
  context if a heavier session warrants it.
- **Notes**: Split GGUF. `--jinja` for the chat template. Same
  parallel-slot treatment as minimax-m27 so cross-lineage comparison
  benefits from prefix-cache stickiness across project conversations.

### minimax-m27: big-brain for hard problems

Two entries, one per usage mode (see "Modes" section below for the full
picture). The earlier IQ3_S entry was dropped after the three-mode design
landed; iq4 covers the coexistence slot at higher quality and q4 covers
solo at top quality, so IQ3 had no remaining role.

| llama-swap entry | Quant | Group | File (shard 1) | Args | ~Disk | ~VRAM live |
|---|---|---|---|---|---|---|
| `minimax-m27-iq4` (alias `minimax-m27`, `minimax:m27`) | UD-IQ4_XS | `code` (coexists with chat) | `UD-IQ4_XS/MiniMax-M2.7-UD-IQ4_XS-00001-of-00004.gguf` | `-c 196608 --parallel 3` | ~95-100 GB | ~135 GB |
| `minimax-m27-q4` (alias `minimax:m27-q4`) | UD-Q4_K_XL | `code-heavy` (exclusive, evicts chat) | `UD-Q4_K_XL/MiniMax-M2.7-UD-Q4_K_XL-00001-of-00004.gguf` | `-c 262144 --parallel 4` | ~115-120 GB | ~185 GB |

- **Source**: `unsloth/MiniMax-M2.7-GGUF`
- **Pull** (split GGUFs per quant directory):
  - `hf download unsloth/MiniMax-M2.7-GGUF --include "*UD-IQ4_XS*.gguf" --local-dir ./UD-IQ4_XS/`
  - `hf download unsloth/MiniMax-M2.7-GGUF --include "*UD-Q4_K_XL*.gguf" --local-dir ./UD-Q4_K_XL/`
- **Why**: 229B / 10B-active MoE. Reserved for problems where the smaller
  models stall (long reasoning chains, hard refactors, tool-call planning).
- **Inference**:
  - iq4 runs at `-c 196608 --parallel 3` (three sticky 64K slots, q8_0
    KV). Live ~135 GB. Sized for coexistence with a chat-tier model
    (qwen3.6 ~36 GB, qwen3.6-flash ~54 GB) inside the 192 GB budget.
  - q4 runs at `-c 262144 --parallel 4` (four sticky 64K slots). Live
    ~185 GB. The `code-heavy` group is `exclusive: true`, so loading
    q4 evicts the chat group; you get max minimax quality at the cost
    of any coresident chat model. (At -c 327680 it OOM'd during MoE
    routing warmup in `ggml_cuda_op_topk_moe`; 64K per slot is the
    stable ceiling.)
- **Notes**: Split GGUFs (too large for HuggingFace's per-file limit).
  Both iq4 and q4 ship as 4 shards each in their per-quant
  subdirectories. llama.cpp handles split GGUFs natively: point
  `--model` at shard 1 and it auto-loads the rest from the same
  directory. `--jinja` is required for the chat template and
  tool-call handling. Sampling values pinned per MiniMax's
  recommendations.

### bge-reranker: RAG reranker

- **File**: `bge-reranker-v2-m3-Q8_0.gguf`
- **Source**: `gpustack/bge-reranker-v2-m3-GGUF`
- **Pull**: `hf download gpustack/bge-reranker-v2-m3-GGUF --include "*Q8_0*.gguf" --local-dir .`
- **Why**: Reranks retrieval hits for OpenWebUI's RAG. Low volume, so it stays
  in llama-swap rather than getting its own container.
- **VRAM**: ~600 MB. Short TTL (300s) so it unloads quickly between bursts.

### embedding models (swap group): for project experimentation

Three GGUF embedding models served via llama-swap under the `embed` group
(`swap: true, exclusive: false`). Only one is resident at a time, but the
group coexists with `chat`, so RAG-style flows that need an embed model plus
a chat model in parallel work without contention. Use these for
domain/quality comparisons in project code; OpenWebUI's always-on RAG
embedding is on TEI (see Embeddings section below).

| llama-swap name | File | Source | ~Disk | ~VRAM live | Pooling |
|---|---|---|---|---|---|
| `bge-m3` | `bge-m3-Q8_0.gguf` | `gpustack/bge-m3-GGUF` | ~600 MB | ~1 GB | `cls` (encoder) |
| `qwen3-embed-0_6b` | `Qwen3-Embedding-0.6B-Q8_0.gguf` | `Qwen/Qwen3-Embedding-0.6B-GGUF` | ~700 MB | ~1.5 GB | `last` (decoder) |
| `qwen3-embed-4b` | `Qwen3-Embedding-4B-Q8_0.gguf` | `Qwen/Qwen3-Embedding-4B-GGUF` | ~4.5 GB | ~6 GB | `last` (decoder) |

- **Pull**:
  - `hf download gpustack/bge-m3-GGUF --include "*Q8_0*.gguf" --local-dir .`
  - `hf download Qwen/Qwen3-Embedding-0.6B-GGUF --include "*Q8_0*.gguf" --local-dir .`
  - `hf download Qwen/Qwen3-Embedding-4B-GGUF --include "*Q8_0*.gguf" --local-dir .`
  - Verify filenames after download; the publishers occasionally tweak case
    or naming (e.g. `f16` vs `F16`, `Q8_0` vs `q8_0`). The `ai_models`
    entries assume the canonical names in the table above.
- **Why**: For embedding benchmark / domain-fit comparisons in project code.
  All three are OpenAI-compatible at `http://max:11434/v1/embeddings` with
  the `model` field set to the llama-swap name or alias.
- **Pooling gotcha**: BGE is encoder-style (`--pooling cls`); Qwen3-Embedding
  is decoder-style (`--pooling last`). Wrong pooling silently returns junk
  vectors with no error. The `args` in `ai_models` are already set
  correctly per model; don't crosswire them.
- **TTL**: 300s per entry: embedding workloads tend to be bursty so the
  short TTL releases VRAM quickly between sessions.

### qwen3-small: CPU-resident compaction model

- **File**: `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`
- **Source**: `unsloth/Qwen3-4B-Instruct-2507-GGUF`
- **Pull**: `hf download unsloth/Qwen3-4B-Instruct-2507-GGUF --include "*Q4_K_M*.gguf" --local-dir .`
- **Why**: Used as opencode's `small_model` for context compaction. Lives
  on CPU (`-ngl 0`) for two reasons: (a) the larger quants fill most of
  the 192 GB VRAM budget once their KV pool is allocated, so a coresident
  GPU model would be tight; (b) compaction needs `persistent: true` to
  avoid a cold-load tax, but the `chat` group is `swap: true` and would
  evict it whenever a chat model swaps in. CPU placement sidesteps both,
  and the `cpu` group keeps the llama-server process warm so compaction
  skips the model-load tax on top of slow CPU prompt processing.
- **RAM**: ~2.5 GB resident; CPU-only via `-ngl 0`. Runs on the 9955WX with
  `--threads 12 --threads-batch 12`. Expect ~200 tok/s prompt processing on
  long inputs, so a 100k-token compaction lands in the 5-8 minute range.
- **Notes**: Not for interactive chat: its `name`/`alias` is intentionally
  not exposed in OpenWebUI's normal model list (no one would pick it). The
  alias `qwen3:4b` exists so opencode can reach it under a friendly name.
  If compaction latency turns out to be too painful, the next escalation is
  the 1.5B variant of this family (~3-4 min on the same hardware).

## Speech-to-text (whisper / speaches, not llama-swap)

Voice input is served by the `whisper` container (speaches), not llama-swap.
The model lives in the `whisper-cache` named volume. Unlike TEI, speaches
does **not** lazy-download on first transcription: without a pre-pull,
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

## Embeddings (always-on, TEI)

Two TEI containers, each pinned to one model. TEI is single-model-per-container
by design, so each "always-on" embedding model adds one container. For
swap-loaded embedding models used in project experimentation, see the
"embedding models (swap group)" section above; those go through llama-swap
on `:11434`.

### tei: OpenWebUI RAG embedding (always-on)

- **Current model**: `Qwen/Qwen3-Embedding-0.6B` (1024-dim, multilingual,
  top-of-MTEB at this size). Read directly from local disk at
  `/opt/docker/ai/models/Qwen3-Embedding-0.6B/` (bind-mounted into the
  container at `/models/Qwen3-Embedding-0.6B`); no HF Hub pull at runtime.
- **History**: Was `nomic-ai/nomic-embed-text-v1.5` until 2026-05-24. Switched
  to consolidate around the Qwen3 family already used elsewhere in the stack,
  get a quality / multilingual bump, and drop the
  `tei_model_revision: e5cf08aa...` pin (which existed only to dodge a TEI
  serde-alias bug in newer nomic config revisions).
- **Endpoint**: `http://192.168.1.100:11435/v1/embeddings`. Consumed by
  OpenWebUI via `open_webui_rag_embedding_base_url` in
  `roles/open_webui/defaults/main.yml`.
- **Re-embed on switch**: collections embedded under one model can't be
  searched with another. Reset OpenWebUI vector storage (Admin -> Documents)
  and re-ingest after the migration.
- **Swap candidates**: `nomic-ai/nomic-embed-text-v2-moe` (multilingual MoE,
  smaller idle footprint), `Snowflake/snowflake-arctic-embed-l-v2.0`
  (multilingual, 1024-dim), or `Qwen/Qwen3-Embedding-4B` for max quality at
  ~7.6 GB resident.

### tei-jina: jinaai/jina-embeddings-v3 (always-on)

- **Current model**: `jinaai/jina-embeddings-v3` (1024-dim, multilingual,
  task-conditioned via LoRA adapters). Read from local disk at
  `/opt/docker/ai/models/jina-embeddings-v3/` (bind-mounted read-only).
- **Why a separate container**: jina-v3's task-specific LoRA adapters and
  `custom_st.py` pooling logic don't translate to a clean GGUF, so llama-swap
  can't serve it. To keep it available without losing the llama-swap embed
  group's swap benefits for the other three, it gets its own dedicated TEI
  container.
- **Endpoint**: `http://192.168.1.100:11436/v1/embeddings`.
- **Idle cost**: ~1.1 GB resident VRAM. Acceptable for the convenience of
  having jina-v3 available alongside the swappable Qwen3 / bge-m3 embedders.

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
