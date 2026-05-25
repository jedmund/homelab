# sglang

SGLang-based inference stack on `max` for models llama.cpp can't serve
(novel attention, large MoEs that need NVFP4 + tensor parallel). Runs
alongside the `ai` role's llama-swap stack rather than replacing it.

| Model | Host port | Image | Quant | GPUs | Notes |
|---|---|---|---|---|---|
| DeepSeek V4 Flash | `11437` | `lavd/sglang-d4f-b12x:5-24` | NVFP4 + FP8 | 2x Blackwell, `--tp-size 2` | Hybrid CSA + HCA attention via `--attention-backend=dsv4`; experimental, see warning below |

### Status: DeepSeek V4 Flash (2026-05-24)

Working, but **the current `lavd/sglang-d4f-b12x:5-24` build has a confirmed A16 MoE kernel accuracy bug**. Outputs may be subtly wrong; do not use for anything where output correctness matters. MTP / speculative decoding is disabled because it exposes the bug more aggressively. Bump the image tag and re-enable the `--speculative-*` flags in `defaults/main.yml` once a newer lavd image with the fix lands.

## Why a separate stack?

The voipmonitor SGLang image bundles SM120 patches, the b12x fused MoE
kernel, and a known-good NCCL graph file. Mixing it into the `ai` role
would have meant either rewriting the llama-swap orchestration or
running two GPU runtimes through the same compose project. Keeping it
as its own stack lets each engine evolve independently.

## Manual lifecycle

Every model in `sglang_models` is gated behind a compose profile.
Ansible deploys the compose file but starts nothing; the operator
brings models up explicitly because a heavy NVFP4 model can pin most
of the 192 GB VRAM budget and the chat/code coexistence catalog under
llama-swap loses VRAM whenever an SGLang model is resident.

```
# Bring DeepSeek V4 Flash up (60-90s cold load)
docker compose -p sglang --profile deepseek-v4-flash up -d

# Tail the startup
docker compose -p sglang logs -f deepseek-v4-flash

# Hand VRAM back to llama-swap when done
docker compose -p sglang --profile deepseek-v4-flash down
```

The OpenAI-compatible endpoint is at `http://max:11437/v1` while the
model is running.

## Model downloads

NVFP4 weights live at `{{ docker_base_path }}/sglang/models/<host_subdir>/`
on the host, mounted into the container at `/models` read-only.

For DeepSeek V4 Flash:

```
cd /opt/docker/sglang/models
hf download canada-quant/DeepSeek-V4-Flash-NVFP4-FP8-MTP \
  --local-dir DeepSeek-V4-Flash-NVFP4-FP8-MTP
```

(The newer `hf` CLI dropped `--local-dir-use-symlinks`; `--local-dir`
already writes plain files. If you're on the older `huggingface-cli`,
add `--local-dir-use-symlinks False`.)

The download is ~140 GB. Confirm checksums by spot-checking a couple of
shards against the HF Hub `file_size` metadata before first launch.

## Layout

```
{{ docker_base_path }}/sglang/
├── compose.yaml         # rendered from templates/compose.yaml.j2
└── models/              # NVFP4 weights, populated out of band
    └── DeepSeek-V4-Flash-NVFP4-FP8-MTP/
```

## Hardware notes

Targets `max` (two RTX PRO 6000 Blackwell, SM120, no NVLink, PCIe Gen5).
`count: all` in the compose service hands the container every GPU the
host exposes; `--tp 2` in the model args splits the model across both.

If you see NCCL deadlocks (GPUs at 100% but ~140 W and no VRAM growth),
try `NCCL_P2P_LEVEL=2` instead of `SYS` in `sglang_common_env`. The FAQ
flags this as a known AMD Turin/Genoa interaction; max is on different
silicon so SYS should hold, but the knob is there if it doesn't.

## Common errors

- **"NaN crash" / "probability tensor contains inf"**: wipe the JIT
  cache (`docker volume rm sglang_jit-cache`) and retry. If it
  recurs, the upstream fix is to swap `--fp4-gemm-backend cutlass` in
  for the default flashinfer backend.
- **"MTP OOM" / model loads twice**: `SGLANG_ENABLE_SPEC_V2=True` is
  missing from the env. The DeepSeek V4 Flash entry sets it; if you
  add another MTP model, copy that pattern.
- **"No valid attention backend"**: SGLang doesn't have an
  implementation for this model's attention class. Different from
  flag-tuning; usually means waiting for upstream support.
