# vLLM

DeepSeek V4 Flash on `max`, published at port `11437` with API model name
`DeepSeek-V4-Flash`, an alternative GLM 5.3 Flash Spark profile on `11438`,
and an optional Qwen Flash Next experiment on GPU 2 at `11439`. The role renders the Compose file and creates cache
directories. Model startup remains an explicit Compose profile action.

## Runtime and model

The `deepseek-v4-flash-0731` profile uses Karmic Kraken beta assembly
`20260920-22f3f98b065ed8de`, pinned by digest in
[defaults](defaults/main.yml). Its unified image entrypoint selects the
`ds4-flash` profile and `rtx-pro-6000-pcie` hardware settings. Native arguments
in `command` override those defaults. It does not use the older
`serve-ds4-flash.sh` entrypoint or its `TP_SIZE`/`DSPARK_TOKENS` aliases.

The checkpoint and code revision are pinned to
`deepseek-ai/DeepSeek-V4-Flash-0731` at
`9e165c30e2704aec5d9d593cce3eebd58bbef1cb`. Preserve that snapshot; the cache's
`main` ref may point to another revision. The image's DSpark profile pins its
draft revision to the same snapshot; verify this through `--print-config`
when updating the image.

| Setting | Configured value |
| --- | --- |
| GPU pair | Max-Q GPUs 0 and 1, ordered by PCI bus |
| Parallelism | TP2, DCP1 |
| Speculation | DSpark, five draft tokens |
| Active request limit | 4 |
| Maximum context | 131,072 tokens |
| Batched token budget | 4,096 |
| GPU memory fraction | 0.975 |
| External cache | Disabled (`CACHE_MODE=vram`) |
| Sampling defaults | Temperature 1, top-p 1 |

The upstream model profile supplies thinking/high reasoning, FP8 attention KV,
B12X attention/MoE, prefix caching, and model-specific graph settings. Check
the effective configuration and actual outputs after updates. The older
Gilded image's reported K7 problems are historical observations; they do not
establish the behavior of every later runtime. This deployment retains K5.

See the [upstream model guide](https://github.com/local-inference-lab/rtx6kpro/blob/master/models/deepseek-v4-flash.md)
and [shared launcher guide](https://github.com/local-inference-lab/rtx6kpro/blob/master/docs/unified-vllm-docker.md).
The selected channel is a pre-release and requires local serving validation.

## Deploy and inspect

Follow [Operations](../../docs/operations.md) and scope the deployment to vLLM.
The host requires a CUDA 13.4-capable NVIDIA driver for this image's native
compilation. See [GPU host maintenance](../gpu_tools/README.md).

```sh
# On the control machine: render configuration; this starts no model.
make deploy-vllm
```

On `max`:

```sh
cd /opt/docker/vllm
docker compose --profile deepseek-v4-flash-0731 config --quiet
docker compose --profile deepseek-v4-flash-0731 pull
docker compose --profile deepseek-v4-flash-0731 up -d
docker compose --profile deepseek-v4-flash-0731 logs -f
curl -fsS http://127.0.0.1:11437/health
curl -fsS http://127.0.0.1:11437/v1/models
```

First K5 startup took about 7.5 minutes for compilation and warmup. The
profile allows ten minutes for startup before counting healthcheck failures;
readiness still requires a successful HTTP response. Read startup logs while
health checks are pending. Confirm the served name,
revision, context, GPU placement, and shared KV capacity. Request slots share
KV memory; four slots do not imply four full-size contexts fit simultaneously.
Test chat, structured JSON, tool calls, code, and long prompts before accepting
an image. Verify LAN reachability and repeat checks after a restart.

The image supports `--print-config` without loading weights. Use the same
profile, environment and native arguments as the rendered service to inspect
its effective launch. For a target-only diagnostic, override `--mode dspark`
with `--mode off --draft-tokens 0` in a temporary Compose command override
while retaining the other arguments. Positive draft tokens conflict with off mode. Restore the normal command before measuring K5 performance.

`make deploy-ai-split` also starts this profile, but redeploys the AI stack.
Use the vLLM-only workflow for a runtime upgrade that should preserve other
GPU services. `ai_split_vllm_profile` retains its existing default name.

## GLM 5.3 Flash Spark alternative

`glm-5.3-flash-spark` uses the same pinned runtime image and the dedicated
`glm53-spark-tp2` preset. The checkpoint is
`local-inference-lab/GLM-5.3-Flash-NVFP4-Spark`, revision
`a608241037e4c2565356bff7ca293f2133888f88`. Target, code, and MTP revisions
are pinned. The API name is `GLM-5.3-Flash` on port `11438`.

The preset supplies TP2/DCP2, MTP3, four request slots, a 3,072-token prefill
budget, FP8 KV, and the two-card memory allocation. Context length is selected
by the runtime from available capacity. Sampling defaults are temperature 1
and top-p .95, with high reasoning. External caching remains disabled.
Its compiler cache is `/opt/docker/vllm/cache/glm53-spark-22f3f98b`.
On September 21, auto-fitting selected 950,272 context tokens and reported
953,418 shared KV tokens. Tests covered up to 120K, including four concurrent
requests. First startup took about 8.7 minutes; a cached restart took 4.7
minutes. These observations are recorded in the
[GLM setup report](../../docs/inference-glm-setup-2026-09-21.md).
See the [upstream two-card recipe](https://github.com/local-inference-lab/rtx6kpro/blob/master/models/glm-5.3-flash-spark-tp2.md).

Download once on `max` using the installed HF CLI. The pinned snapshot is
about 188 GB; reserve additional space for runtime caches:

```sh
~/.local/bin/hf download local-inference-lab/GLM-5.3-Flash-NVFP4-Spark \
  --revision a608241037e4c2565356bff7ca293f2133888f88 \
  --cache-dir /home/justin/.cache/huggingface/hub
```

Both models occupy GPUs 0 and 1. Run only one at a time; do not use
`--profile all up`. Switch on `max` after rendering with `make deploy-vllm`:

```sh
cd /opt/docker/vllm
docker compose --profile deepseek-v4-flash-0731 stop deepseek-v4-flash-0731
docker compose --profile glm-5.3-flash-spark up -d --pull never glm-5.3-flash-spark
curl -fsS http://127.0.0.1:11438/health
curl -fsS http://127.0.0.1:11438/v1/models
```

Wait for readiness before using the API. To return to DeepSeek:

```sh
cd /opt/docker/vllm
docker compose --profile glm-5.3-flash-spark stop glm-5.3-flash-spark
docker compose --profile deepseek-v4-flash-0731 up -d --pull never deepseek-v4-flash-0731
curl -fsS http://127.0.0.1:11437/health
```

The split deployment workflow can select GLM with
`-e ai_split_vllm_profile=glm-5.3-flash-spark` passed to
`ansible-playbook deploy/ai_split.yml -e ai_gpu_mode=split`; this also redeploys
the AI stack. Its default remains DeepSeek. Normal `deploy/all.yml` applies
the AI role in split mode and does not render or switch vLLM profiles.
The pinned model profiles are preserved by subsequent vLLM renders.

## Qwen Flash Next on GPU 2

`qwen3.8-flash-next` uses the pinned Karmic image with profile
`qwen38-flash-next`, TP1/DCP1 and MTP3. The checkpoint is
`local-inference-lab/Qwen3.8-Flash-Next-NVFP4`, pinned for target/code/draft
at `7c4f1bc1a2d6847e0cbc01ac6b823f00251de8dd`. The API model name is
`Qwen3.8-Flash-Next` on port `11439`.

This text-only experiment uses four request slots and a .90 GPU memory
fraction to leave space for TEI, Whisper and emulator services. Its profile
moves PLE tables into host RAM; this allocation is separate from prompt
caching. External RAM/disk prompt caching stays disabled. The configured
context limit is 262,144 tokens. The first local startup reported 369,715
shared KV tokens; four slots do not each receive a full context allocation.
Runtime caches live in `/opt/docker/vllm/cache/qwen38-next-22f3f98b`.
See the [upstream profile](https://github.com/local-inference-lab/rtx6kpro/blob/master/models/qwen38-flash-next.md).

Local testing passed API checks and isolated 120K retrieval, but combined
long-prompt/decode traffic caused a CUDA illegal-memory-access crash. Short
decode was slower than the existing llama-swap model. Keep this profile
experimental and stopped during normal use; see the
[comparison and limitations](../../docs/inference-qwen-setup-2026-09-21.md).
First startup took 10.5 minutes; cached startup took 4.8 minutes.

Download the 106-GB checkpoint on `max` before starting:

```sh
~/.local/bin/hf download local-inference-lab/Qwen3.8-Flash-Next-NVFP4 \
  --revision 7c4f1bc1a2d6847e0cbc01ac6b823f00251de8dd \
  --cache-dir /home/justin/.cache/huggingface/hub
```

Render with `make deploy-vllm`, then on `max`:

```sh
# Stop the model loader so incoming requests cannot load a competing model.
docker stop llama-swap
cd /opt/docker/vllm
docker compose --profile qwen3.8-flash-next up -d --pull never qwen3.8-flash-next
curl -fsS http://127.0.0.1:11439/health
curl -fsS http://127.0.0.1:11439/v1/models
```

Wait for readiness before testing. DeepSeek can remain running on GPUs 0 and 1.
Monitor host RAM and the GPU 2 side services during the experiment. Restore
normal model-switching and OCR service afterward:

```sh
cd /opt/docker/vllm
docker compose --profile qwen3.8-flash-next stop qwen3.8-flash-next
docker start llama-swap
curl -fsS http://127.0.0.1:11434/health
```

A normal AI deployment stops a running Qwen experiment before starting
llama-swap. The split-pair workflow rejects Qwen as `ai_split_vllm_profile`;
use this manual GPU 2 workflow instead. Do not run `--profile all up`.

## Storage and networking

The existing mounts remain:

- `/home/justin/.cache/huggingface` for model weights.
- `/home/justin/.cache/deepseek` for the broader existing cache mount.
- `/opt/docker/vllm/cache/ds4-karmic-22f3f98b` for the new runtime/compiler cache.
- `/opt/docker/vllm/cache/ds4-v20-r15` retained for the prior runtime.

The profiles use host IPC and `gpus: all`. DeepSeek/GLM select
`CUDA_VISIBLE_DEVICES=0,1`; Qwen selects GPU 2 and requires llama-swap stopped.
GPU 2 normally belongs to llama-swap and the AI side services. Preserve
`amd_iommu=pt iommu=pt` on the host. Port publication remains `11437:11437`;
switching to host networking requires a separate firewall review.

On a replacement host, stage the pinned checkpoint with an installed HF CLI:

```sh
hf download deepseek-ai/DeepSeek-V4-Flash-0731 --revision 9e165c30e2704aec5d9d593cce3eebd58bbef1cb
```

Check available storage first. Do not prune the old image, model snapshot,
or compiler cache while validating its replacement.

## Recovery

Before replacing an image, save the working Compose file with its image
reference pinned by digest. Keep its absolute mounts and project name. The
September 21 pre-upgrade file is stored on `max` at
`/home/justin/.cache/inference-upgrade/20260921/vllm-r15-rollback.compose.yaml`.
It preserves Gilded Gnosis r15, the same model snapshot, and the old cache.

To restore that recorded configuration on `max`:

```sh
cd /opt/docker/vllm
docker compose --profile deepseek-v4-flash-0731 stop deepseek-v4-flash-0731
sudo cp /home/justin/.cache/inference-upgrade/20260921/vllm-r15-rollback.compose.yaml compose.yaml
docker compose --profile deepseek-v4-flash-0731 up -d --pull never
```

Repeat readiness, output, and LAN checks. Restore the matching repository
configuration before another Ansible render, or it will overwrite the rollback.
A saved configuration is not proof of successful recovery; record the result
when rollback is exercised.

For CUDA error 803 after a host driver upgrade, see the
[generated compatibility-library repair](../gpu_tools/README.md#existing-containers-after-a-driver-change).

## Clients and records

The Linux agent clients use `DeepSeek-V4-Flash` at port 11437 and advertise
131,072 context tokens. Those identifiers remain unchanged. Client-selected
reasoning effort and interactive client workflows require separate validation.

- [Qwen GPU 2 experiment](../../docs/inference-qwen-setup-2026-09-21.md)
- [GLM setup and checkout synchronization](../../docs/inference-glm-setup-2026-09-21.md)
- [Runtime upgrade and validation](../../docs/inference-runtime-upgrade-2026-09-21.md)
- [Original R580/r15 baseline](../../docs/inference-baseline-2026-09-21.md)
- [Driver and kernel maintenance](../../docs/inference-driver-upgrade-2026-09-21.md)
- [Ordered inference upgrade plan](../../docs/inference-upgrade-plan.md)
