# vllm

The active DeepSeek V4 Flash serving path on `max`, port `11437`. Two
model profiles live in this stack:

| Profile | Checkpoint | Image | Status |
|---|---|---|---|
| `deepseek-v4-flash` | `deepseek-ai/DeepSeek-V4-Flash` (preview) | `lavd/vllm:jasl-dsv4-5-21-13.2` | Known-good, current default |
| `deepseek-v4-flash-0731` | `deepseek-ai/DeepSeek-V4-Flash-0731` | `voipmonitor/vllm:gilded-gnosis-v20-...-r15` | New, unvalidated on this box |

Both bind host port `11437`, so only one runs at a time. That is
intentional: an accidental double-start fails loudly rather than
quietly splitting VRAM across two servers.

Ansible renders the compose file but starts nothing. Bringing a model
up is an explicit operator action.

## Which profile deploys

`deploy/ai_split.yml` starts whichever profile `ai_split_vllm_profile`
names, defaulting to `deepseek-v4-flash` (the preview). Nothing about
the existing deploy changes until that default is flipped.

```bash
# Preview, unchanged behaviour
make deploy-ai-split

# 0731 instead, same command otherwise
ansible-playbook -i inventory deploy/ai_split.yml \
  -e ai_gpu_mode=split -e ai_split_vllm_profile=deepseek-v4-flash-0731
```

By hand on max:

```bash
cd /opt/docker/vllm
docker compose --profile deepseek-v4-flash-0731 up -d
docker compose --profile deepseek-v4-flash-0731 logs -f
docker compose --profile deepseek-v4-flash-0731 down
```

## Two different image contracts

The lavd image's ENTRYPOINT invokes `vllm serve`, so the preview entry
passes everything through `args` as argv.

The voipmonitor gilded-gnosis image instead ships
`/usr/local/bin/serve-ds4-flash.sh` as ENTRYPOINT and takes every
serving choice from environment variables. That entry sets
`entrypoint`, `network_mode: host`, `privileged: true`, and an
`extra_env` block, and omits `args` entirely. The compose template
branches on which fields are present, so both shapes coexist.

Upstream reference for the 0731 entry is
`examples/docker-compose-ds4-v20-r15.yml` in
[local-inference-lab/blackwell-llm-docker](https://github.com/local-inference-lab/blackwell-llm-docker).
That repo's `build-gilded-gnosis-v20-final-cu132.sh` is the source of
truth for image tags: each revision is pinned there with its vLLM and
SparkInfer tree hashes.

## DSPARK_TOKENS must be 5, not 7

Both the DeepSeek model card and the upstream compose example default
DSpark to `num_speculative_tokens: 7`. **7 produces garbled output.**
Multiple operators running 2x RTX PRO 6000 confirmed this on release
day (2026-07-31) and isolated it to the token count; 5 works across
the board. It shows up most readily above roughly 16 concurrent
sequences, so a low-concurrency config can carry the bug latently and
only expose it later when concurrency is raised.

Our entry pins `DSPARK_TOKENS: "5"` and starts at `MAX_NUM_SEQS: "4"`.
If you raise concurrency, re-check output quality at each step rather
than assuming the config is still safe.

`MODE=mtp2` / `MODE=mtp3` do not serve 0731. The launcher falls back
to the older preview checkpoint for those, because 0731 does not
provide the standard MTP serving contract. `MODE=dspark-mtp0` gives a
no-speculation baseline on the 0731 weights, which is the right first
bring-up step.

## Bring-up sequence for 0731

1. `make deploy-vllm` to render the compose file (starts nothing).
2. Pull the image on max. It is about 12.5 GB.
3. First start with `MODE=dspark-mtp0` to take speculative decoding out
   of the picture entirely, and confirm coherent output.
4. Switch back to `MODE=dspark` with `DSPARK_TOKENS=5` and re-check.
5. Only then raise `MAX_NUM_SEQS`, re-checking output each step.
6. Flip `ai_split_vllm_profile` once it holds.

## VRAM budget

0731 is about 167 GB of weights against the Max-Q pair's 192 GB, up
from the preview's roughly 150 GB. That leaves noticeably less room
for KV cache, activations, and CUDA graphs.

`GPU_MEMORY_UTILIZATION` is set to `0.975` (upstream's value) rather
than the preview's `0.96` to claw some of that back. If it OOMs at
load, pin explicit `cudagraph_capture_sizes` to cap graph memory
before reaching for a lower utilization.

Weights download into the HF cache at
`/home/<user>/.cache/huggingface`. As of 2026-07-31 that cache holds
150 GB and `/` has 459 GB free, so both checkpoints fit. Consider
evicting the preview snapshot once 0731 is confirmed.

## Hardware notes

See `roles/sglang/README.md` for the shared hardware caveats that
apply to this box: the `amd_iommu=pt iommu=pt` kernel cmdline
requirement, and why `gpus: all` is used instead of the newer
`deploy.resources.reservations.devices` syntax.
