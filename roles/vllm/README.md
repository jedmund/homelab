# vllm

The active DeepSeek V4 Flash serving path on `max`, port `11437`.

| Profile | Checkpoint | Image | Status |
|---|---|---|---|
| `deepseek-v4-flash-0731` | `deepseek-ai/DeepSeek-V4-Flash-0731` | `voipmonitor/vllm:gilded-gnosis-v20-...-r15` | Validated on this box, the only profile |

An earlier profile served `deepseek-ai/DeepSeek-V4-Flash`, the rolling
repo pinned at revision `60d8d70770c6776ff598c94bb586a859a38244f1`
(2026-06-23). It was retired once 0731 was validated here, and its
149 GB of weights were removed from the HF cache. 0731 is the current
official release and supersedes it.

That revision is recorded because it is the only way back: the weights
were never staged on the NAS, and the repo is a rolling one, so pulling
`deepseek-ai/DeepSeek-V4-Flash` today gives whatever is current rather
than what we ran. Recovery means fetching that specific revision.

Ansible renders the compose file but starts nothing: the model is gated
behind a compose profile, so bringing it up is an explicit action. The
profile mechanism is kept even with one model, both because starting a
~165 GB model should never be an accident of running a deploy, and
because it leaves room for a second checkpoint at the next release.

## Which profile deploys

`deploy/ai_split.yml` starts whichever profile `ai_split_vllm_profile`
names, defaulting to `deepseek-v4-flash-0731`:

```bash
make deploy-ai-split
```

The play stops any other running model profile first, so the deploy is
declarative: whatever was running before, the configured profile is what
is running after. Every profile binds 11437, so without that step a
switch fails on a port conflict and silently leaves the old checkpoint
serving.

By hand on max:

```bash
cd /opt/docker/vllm
docker compose --profile deepseek-v4-flash-0731 up -d
docker compose --profile deepseek-v4-flash-0731 logs -f
docker compose --profile deepseek-v4-flash-0731 down
```

## Two different image contracts

The compose template supports two image shapes, because the retired
preview used the first and 0731 uses the second; the branch is kept so a
future `args`-style checkpoint drops in without template changes.

An `args`-style image's ENTRYPOINT invokes `vllm serve` and takes argv.

The voipmonitor gilded-gnosis image instead ships
`/usr/local/bin/serve-ds4-flash.sh` as ENTRYPOINT and takes every
serving choice from environment variables. That entry sets
`entrypoint`, `privileged: true`, and an `extra_env` block, and omits
`args` entirely. The compose template branches on which fields are
present, so both shapes coexist.

We deliberately diverge from upstream's reference compose on one
point: it runs host-networked, we publish `11437:11437` instead.
Docker port publishing installs a DOCKER-chain iptables rule that is
traversed before ufw's INPUT rules, so published ports are reachable
on the LAN. Host networking publishes nothing, so ufw's default deny
applies and LAN clients get dropped unless 11437 is opened explicitly
in `roles/firewall`. Publishing keeps reachability identical to the
preview with no new firewall rule. The template still supports
`network_mode` for future launcher-style images; no model uses it
today.

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

## Download the weights first

The 0731 weights are **not** on max as of 2026-07-31. The cache holds
only the preview (149 GB). Starting the 0731 profile without staging
the weights first makes the container download about 167 GB from HF
Hub before it can serve, with the container sitting unhealthy for the
duration (the 180s healthcheck `start_period` is nowhere near enough).

Stage it out of band instead, so the transfer is resumable and
decoupled from a container start:

```bash
# on max
hf download deepseek-ai/DeepSeek-V4-Flash-0731
```

That lands in `~/.cache/huggingface/hub`, which the compose file
bind-mounts, so the container then only re-validates the snapshot.

Disk check before starting: 149 GB (preview) + 167 GB (0731) is 316 GB
against 459 GB free on `/`, leaving roughly 143 GB. It fits, but evict
the preview once 0731 is confirmed rather than keeping both
indefinitely.

## Bring-up sequence for 0731

1. `make deploy-vllm` to render the compose file (starts nothing).
2. Pull the image on max. It is about 12.5 GB.
3. Download the 0731 weights (see above). This is the long pole.
4. First start with `MODE=dspark-mtp0` to take speculative decoding out
   of the picture entirely, and confirm coherent output.
5. Switch back to `MODE=dspark` with `DSPARK_TOKENS=5` and re-check.
6. Only then raise `MAX_NUM_SEQS`, re-checking output each step.
7. Flip `ai_split_vllm_profile` once it holds.

`LOAD_FORMAT: instanttensor` is upstream's default and is a faster
weight loader, not a separate on-disk artifact we need to produce.
Upstream documents no conversion step, but if the first load errors on
the format, `LOAD_FORMAT=auto` is the fallback to isolate it.

## Client configs

`roles/agents_linux` deploys opencode and pi configs that point at
`max:11437` directly. Two couplings matter when swapping profiles:

- **Model id.** Both clients key off `DeepSeek-V4-Flash`. The 0731
  entry pins `SERVED_MODEL_NAME` to that same value, and the launcher
  honours it: the engine config reports
  `served_model_name=DeepSeek-V4-Flash` on the 0731 profile. Clients
  need no edit when swapping profiles, and equally cannot tell which
  checkpoint they are talking to. Check server-side with
  `docker ps --filter name=deepseek`.
- **Context window.** Both clients advertise `vllm_max_context`
  (`roles/agents_linux/defaults/main.yml`), now 131072 to match the
  0731 profile's `MAX_MODEL_LEN`. Raise it back to 524288 if
  `ai_split_vllm_profile` goes back to the preview, which sets no cap.
  A client value above the server's `max_seq_len` gets requests
  rejected server-side rather than truncated locally.

Unresolved: 0731 adds low/high/max reasoning effort, and the preview
baked `reasoning_effort: high` into `--default-chat-template-kwargs`.
We no longer control argv under the launcher, and only the GLM
launcher in the upstream repo is visibly setting chat-template-kwargs.
Both clients currently declare `supportsReasoningEffort: false`. How
effort is selected under `serve-ds4-flash.sh` needs checking on first
start, and it matters: operators reported a material quality gap
between `high` and `max` on audit-style tasks.

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
