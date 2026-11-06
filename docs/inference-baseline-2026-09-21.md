# Inference baseline: September 21, 2026

This records the first stage of the [inference upgrade plan](inference-upgrade-plan.md).
Measurements target `max` (`atelier-max`). These are dated observations,
not assertions about future host state.

## Host and rollback inventory

| Item | Observed value |
| --- | --- |
| Operating system | Ubuntu 24.04.5 LTS, kernel 6.8.0-139-generic |
| NVIDIA driver | 580.178.04, open server kernel modules; `nvidia-smi` reports CUDA 13.0 |
| GPUs 0 and 1 | RTX PRO 6000 Blackwell Max-Q, 97,887 MiB each, 300 W limit each |
| GPU 2 | RTX PRO 6000 Blackwell Workstation, 97,887 MiB, 600 W limit |
| GPU topology | All three on NUMA node 0; pairwise links reported as NODE |
| Host memory before DeepSeek startup | 125 GiB total, 113 GiB available; no swap in use |
| Local disk before DeepSeek startup | 1.8 TB filesystem, 479 GB available |
| Shared memory | 63 GiB available before startup |
| DeepSeek container on arrival | Stopped, exit code 0, no recorded OOM |
| GPU 2 usage on arrival | About 1.9 GiB; AI side services and llama-swap running |

The existing DeepSeek container was started for measurement without pulling
an image, recreating the container, or changing its configuration. No driver,
power-limit, clock, or model change was applied.

| Serving setting | Value |
| --- | --- |
| Image tag | `voipmonitor/vllm:gilded-gnosis-v20-vllm0bc48c5-sieec30ff-fi801d57a-cu132-20260731-r15` |
| Local image ID and repository digest | `sha256:e5c9d250b211d240b0939b7083305478e9f1ba65c2282b294add4a592e45d282` |
| Checkpoint | `deepseek-ai/DeepSeek-V4-Flash-0731` |
| Loaded revision, confirmed in startup log | `9e165c30e2704aec5d9d593cce3eebd58bbef1cb` |
| API | `max:11437`, model name `DeepSeek-V4-Flash` |
| GPUs / parallelism | GPUs 0 and 1; TP2, DCP1 |
| Speculation | DSpark, fixed K5 |
| Attention cache | FP8, GPU prefix caching enabled, no external cache configured |
| Request slots / context limit | 4 / 131,072 tokens |
| Shared KV capacity reported at startup | 154,127 tokens |
| Batch budget / memory fraction | 8,192 tokens / 0.975 |
| Reasoning default | Thinking enabled, effort `high` |
| Generation defaults | Temperature 1.0, top-p 1.0 |
| Runtime cache | `/opt/docker/vllm/cache/ds4-v20-r15` |
| Model cache | `/home/justin/.cache/huggingface` |
| Restart policy | `no` |

Both cached snapshots have 48 safetensors shard links with no missing targets.
This checks presence, not complete weight hashes. The cache's `main` reference
is `7872f01b1d1fe23eabc4c98b48bffcef5a386062`, which is different from the
loaded revision. Preserve the loaded snapshot and image for rollback.

## API checks

Synthetic prompts were sent through an SSH tunnel from the control machine.
The API model list was also reachable directly over the LAN. Requests used
temperature 0.6, top-p 0.95, seed 42, high reasoning, and an 8,192-token output
cap. All four completed without hitting the output cap.

| Check | Result |
| --- | --- |
| Short chat explanation | Coherent distinction between volatile RAM and persistent disk storage |
| Small coding task | Returned a correct order-preserving deduplication function for hashable items; reviewed without executing model output |
| JSON schema | Returned exactly the expected counts for web and database servers |
| Required tool call | Selected `service_status` with the expected `inference` argument |

These are basic API checks, not a model-quality benchmark or a test of the
interactive opencode, pi, or OpenWebUI clients.

## Performance measurement method

The benchmark is [llm-inference-bench at commit ccd9ad8][bench-pin]. Its
self-update check is disabled by an external wrapper; benchmark source is
unchanged. Raw requests, outputs, dependency versions, commands, and benchmark
results were collected outside the repository at
`/tmp/homelab-inference-baseline-20260921` on the control machine. A retained
archive is stored on `max` at
`/home/justin/.cache/inference-upgrade/20260921/baseline-20260921.tar.gz`.
Retain this archive for the later comparison; raw output is not committed.

The comparison used three warmed 30-second windows per supported
cell, concurrency 1/2/4, and prompt lengths 0/32,768/120,000. The short-context
case still has the benchmark's small instruction prompt. Exact lengths are
checked with the server's tokenizer. Output is capped at 4,096 tokens per
request; the 120,000-token case leaves room within the context limit.

The shared KV budget is explicitly set to the startup value of 154,127 tokens.
Two and four simultaneous 120,000-token requests exceed that budget and are
excluded. Four slots must not be interpreted as four full-length contexts.

Performance requests use temperature 1.0 and server defaults for top-p and
reasoning. Decode windows use the benchmark's default `ignore_eos` behavior
and repetition detection. Prefill scouts measure fresh prompt processing;
decode request latency can benefit from the existing GPU prefix cache.

The benchmark runs over an SSH tunnel and its local hardware sampler is off.
Its startup P2P diagnostic refers to the control machine, not `max`, and is
not used as host evidence. GPU observations are collected separately over SSH.
Other services and a CI runner remain on the host, so this is an operational
baseline rather than an isolated hardware benchmark.

## Performance results

Values below are aggregate output tokens per second across the active
requests. `LOOP` means repetition detection invalidated the window; no speed
is reported for that window. All results are retained, including failures.

| Prompt tokens | Requests | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| Short | 1 | 195.0 | 194.5 | 195.4 |
| Short | 2 | 291.4 | 287.6 | 283.0 |
| Short | 4 | 422.9 | 415.6 | 422.4 |
| 32,768 | 1 | 246.8 | LOOP | 196.4 |
| 32,768 | 2 | 279.3 | 285.5 | 285.7 |
| 32,768 | 4 | 434.9 | 410.0 | 421.5 |
| 120,000 | 1 | 225.7 | LOOP | 189.7 |

Two and four requests at 120,000 tokens were excluded by the shared memory
budget in all three runs. Of the 21 measured windows, 19 produced valid
speed results and two were invalidated by repetition. No measured window
was marked as having insufficient active requests or a warmup timeout.

Short-context medians are 195.0, 287.6, and 422.4 aggregate tokens/sec at
one, two, and four requests respectively. Do not treat the successful
single-request long-context windows as a reliable baseline while ignoring
their failed repeat or the large variation between successful runs.

| Fresh prompt processing | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| 32,768 tokens: seconds to first token | 3.129 | 3.108 | 3.105 |
| 32,768 tokens: input tokens/sec | 10,472 | 10,543 | 10,554 |
| 120,000 tokens: seconds to first token | 12.499 | 12.790 | 12.836 |
| 120,000 tokens: input tokens/sec | 9,601 | 9,382 | 9,349 |

These are one fresh prefill scout per context per run. They are separate
from cached decode-request latency and do not establish output quality.

During a sampled load interval, GPU 0/1 memory clocks were 13,365 MHz and
temperatures were 84/86 C. Both reported an active software power cap and
no active software or hardware thermal slowdown at that observation. The
power limits remained 300 W. No overclock or power adjustment was applied.

### Repetition follow-up

The two failed windows generated repeated text in the content channel.
The benchmark supplies architecture reference text but asks for a long
history of mathematics, while forcing generation past normal end-of-sequence
tokens. Failure excerpts included repeated refusals to answer from the
unrelated reference. This suggests a workload/stopping interaction, but
does not establish the cause or rule out a runtime problem.

The loop guard was kept enabled. A separate control used the same benchmark
with normal stopping: two measured requests at each long context, after one
warmup request. There were no detected loops or request errors, but all four
measured requests reached 4,096 output tokens. This does not establish natural
completion or explain the original failures.

Separate retrieval checks placed a synthetic recovery code in the middle of
a long document and asked the model to return it. Both returned the exact
expected code and finished with `stop`, using the API-check sampling settings.

| Actual prompt tokens | Output tokens, including reasoning | Result |
| --- | --- | --- |
| 32,767 | 94 | Correct, natural stop |
| 120,000 | 74 | Correct, natural stop |

The 120,000-token retrieval request reused 12,288 prefix tokens from GPU
cache, so its latency is not a cold-prefill measurement. These checks establish
basic retrieval only; they do not establish complex long-context reasoning
quality or clear the failed benchmark windows.

Keep the original failures available for comparison rather than suppressing
the loop guard or replacing them with successful retries.

### Operations handoff task

A separate task asked for a 500–700-word operations handoff from the synthetic
maintenance document, with observations separated from recommendations and
the exact recovery code included. Three sequential requests were made at each
context using the API-check sampling settings and an 8,192-token output cap.

| Prompt tokens | Cached prefix tokens | Median first-token time | Median complete-answer time |
| --- | --- | --- | --- |
| 32,823 | 32,512 | 0.288 seconds | 5.798 seconds |
| 120,056 | 119,808 | 0.446 seconds | 6.694 seconds |

All six answers stopped naturally, included the correct code, and met the
requested word count. Output ranged from 967 to 1,126 tokens including
reasoning. These are warm GPU-prefix-cache results, not fresh-document
processing times or LMCache measurements.

Manual review of the first answer at each context found unsupported claims
that checks succeeded and the system was healthy. The source describes
checks but does not establish those outcomes. These responses therefore do
not pass the requested separation of observations from recommendations.
Preserve this task as a quality comparison for candidate models; correct
formatting, retrieval, and fast completion did not establish factual fidelity.

## End state

DeepSeek was left running and healthy on the original image and R580 driver.
Its recorded restart count was zero and no OOM was reported. Existing AI
side services and the emulator container remained healthy; CI jobs continued
during the work. Interactive clients, a full-day soak, and rollback after an
actual image or driver replacement remain untested.

## Next prerequisite

The reviewed [shared Karmic Kraken guide][shared] requires CUDA 13.4-capable
driver support for native JIT compilation. The installed driver reports
CUDA 13.0. [NVIDIA's release notes][cuda] associate CUDA 13.4 with R615;
general CUDA 13.x minor compatibility does not establish that this specific
runtime's JIT paths work on R580.

The host's existing system APT metadata offers drivers through R610 in the
queried branches, but no R615 candidate. A separate temporary APT configuration
was then used to refresh signed Ubuntu and official NVIDIA metadata, without
changing system sources or installed packages.

The pinned R615 package transaction resolved successfully. Candidate and
rollback packages are staged under
`/home/justin/.cache/inference-upgrade/20260921` on `max`. See the
[GPU host maintenance procedure](../roles/gpu_tools/README.md#r615-maintenance-on-max)
for the exact candidate, package changes, checks, and recovery limits.

At the end of this baseline, driver installation and reboot were still pending.
Subsequent authorized maintenance is recorded separately in the
[driver and kernel maintenance record](inference-driver-upgrade-2026-09-21.md).

[bench-pin]: https://github.com/local-inference-lab/llm-inference-bench/tree/ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f
[shared]: https://github.com/local-inference-lab/rtx6kpro/blob/master/docs/unified-vllm-docker.md
[cuda]: https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/
