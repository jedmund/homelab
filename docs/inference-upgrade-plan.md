# Local inference upgrade plan

Prepared September 21, 2026, from the Local Inference Lab repositories and
this repository's configuration. No host inspection or deployment has been
performed when this plan was written. Upstream versions and recommendations
must be checked again when implementing it.

Work has begun: see the [September 21 baseline record](inference-baseline-2026-09-21.md)
for host observations, checks, and the driver prerequisite for the new runtime.
Host inspection, basic API checks, and three benchmark passes are recorded.
Two long-context stress windows failed repetition checks; simple long-context
retrieval passed. A separate operations-handoff baseline completed naturally,
but reviewed answers added unsupported claims of healthy service state.
Retain those quality failures when comparing candidate runtimes and models.

R615 and Ubuntu HWE kernel 7.0.0-31 are installed. Service checks passed
after both reboots, including a repair of stale generated CUDA loader entries
in the existing DeepSeek container. Driver-only short-context medians were
about 2–6% lower than the original baseline; the reduced warmup differs.
Karmic Kraken is deployed with the same model and a 4,096-token prefill budget.
API and throughput checks passed, including two simultaneous 120K requests.
Shared KV capacity increased to 338,122 tokens; decode speed is broadly similar,
and handoff quality limitations remain. Cached restart and repeat Compose
checks passed. Interactive client use and a rollback drill remain untested;
see the [runtime upgrade record](inference-runtime-upgrade-2026-09-21.md).
See the [host maintenance record](inference-driver-upgrade-2026-09-21.md).

The aim is to improve everyday response time and reliability on `max`, then
try other models that fit the existing GPUs. Change one thing at a time so
we can tell what helped and return to the working setup if needed.

## Starting point

[AI defaults](../roles/ai/defaults/main.yml) describe three 96-GB RTX PRO
6000 Blackwell cards. Split mode gives the two Max-Q cards, GPUs 0 and 1,
to vLLM and GPU 2 to llama-swap. Some older hardware notes disagree with
these defaults; confirm the actual hardware before testing.

At the start, [vLLM defaults](../roles/vllm/defaults/main.yml) selected
DeepSeek-V4-Flash-0731 on the July 31 Gilded Gnosis r15 image, port `11437`, with the API model name
`DeepSeek-V4-Flash`. The configuration allows four simultaneous requests and
131,072 tokens of context. DSpark K5 means the server proposes up to five
draft tokens at a time and checks them with the main model.

Keep the current GPU split, client address, model name, model weights, and
working image available throughout the runtime comparison. Leave the parked
SGLang experiment outside this first upgrade.

## Order of work

| Step | Work | Result needed before moving on |
| --- | --- | --- |
| 1 | Inspect the host and record today's performance | A repeatable baseline and a usable rollback |
| 2 | Try a newer runtime with the same DeepSeek model | Correct output, working clients, and acceptable performance |
| 3 | Test reusable prompt storage in RAM, then on disk | Faster repeated prompts with correct recovery |
| 4 | Try GLM Spark on the two-card pair | A measured decision about an alternative to DeepSeek |
| 5 | Try Qwen Flash Next on the third card | A measured decision about an alternative to llama-swap chat |
| 6 | Keep the useful changes and update the runbooks | Pinned, documented settings with a tested rollback |

Steps 4 and 5 are optional model experiments. A runtime or caching improvement
can be kept without changing the model we use daily.

## 1. Inspect and measure the current setup

- Confirm GPU identities, memory, driver version, running containers, and
  which services occupy each GPU. Check available RAM and local disk space.
- Record the actual image digest, model revision, launch settings, GPU clocks,
  and power limits. Preserve the working image and weights; do not prune them.
- Choose a small set of representative prompts: normal chat, a coding task,
  a tool call, structured JSON, and a long conversation or document.
- Measure time until the first token, generation speed, and completed-answer
  quality. Test one, two, and four simultaneous requests at short, 32K, and
  128K contexts where capacity permits. Record failures and capacity limits.
- Repeat measurements after warmup. Keep prompts, sampling settings, output
  limits, and hardware settings the same in later comparisons. Store raw
  results outside tracked paths and keep credentials and private prompts out
  of committed reports.

Use a pinned version of [llm-inference-bench][bench] for the performance
comparison. Its repetition detection and latency measurements are useful,
but our actual client workflows must also pass.

**Done when:** the baseline can be repeated, the old profile can be restored,
and we have agreed which response times and output behavior are acceptable.

## 2. Upgrade the runtime while keeping DeepSeek

Evaluate a pinned release of the shared [Karmic Kraken image][shared] using
the [DeepSeek text profile][deepseek]. At the review date this is a beta
integration channel, not a stable-release guarantee. Check its current
release notes, published image, and known issues before selecting a version.

This is more than an image-tag change: the new image has a different launch
interface. Adapt the vLLM role to that interface and preserve port `11437`,
the `DeepSeek-V4-Flash` API name, GPU selection, and existing storage paths.
Keep model startup explicit through Compose profiles. Give the candidate a
separate runtime/compiler cache while reusing the existing model download.

The reviewed image uses CUDA 13.4.1. Its guide requires a driver for which
`nvidia-smi` reports CUDA 13.4 or higher for native compilation. If our driver
is too old, plan and validate that host upgrade separately before proceeding.
Check the other GPU services after a driver change as well.

Start with external RAM/disk caching off, the same checkpoint, and the current
request and context limits. Check output with speculation off, then enable
the documented DSpark K5 profile. Do not copy older tuning variables without
checking whether the new launcher still supports them.

Run the baseline again, test LAN clients, and check behavior through a restart
and a normal working day. The lab's latest comparison improved concurrent
DeepSeek throughput but slightly reduced single-request speed; its overclocked
results are not a prediction for our host. See the [measurement report][results].

**Done when:** client workflows and output checks pass, the service remains
stable, and measured benefits justify any regression. Otherwise stop the
candidate and restore the recorded image, profile, and runtime cache.

## 3. Reuse long prompts from RAM, then disk

Keep the accepted runtime and model fixed. Enable LMCache with a bounded RAM
budget based on the host's free memory. It stores reusable prompt prefixes,
so repeated requests can avoid processing the same text again. It does not
increase the active context window or make model weights fit in less VRAM.

Compare a fresh prompt, an identical repeat, and a prompt with an edit near
the end. Also edit an earlier section to check that changed text is processed
correctly. Compare answers as well as time until the first token.

Add a bounded disk tier only if RAM reuse helps and local storage has enough
space. Test recovery after restarting both inference and cache services.
Account for shared-memory use and cache-service ports. Keep cache integration
in the owning inference role and use separate runtime storage for each model.

**Done when:** repeated prompts are materially faster, edited prompts produce
correct answers, and recovery works without exhausting RAM or disk. Disable
external caching if it adds complexity without helping our workload.

## 4. Try GLM Spark as an alternative on the pair

GLM Spark is downloaded and configured as an optional profile. API checks,
32K/120K retrieval, and one short/long stress pass passed, including four
simultaneous 120K requests. It was slower on short decode, and handoff tests
still failed length/factuality requirements. Keep DeepSeek as the default;
see the [GLM setup record](inference-glm-setup-2026-09-21.md) for measurements
and checkout synchronization. Cached restart and repeat Compose checks passed.

Use the dedicated [GLM-5.3-Flash Spark two-GPU preset][glm]. It is a specific
checkpoint and memory configuration for two 96-GB cards; changing the normal
four-GPU profile to two GPUs is not equivalent.

Stop DeepSeek before loading GLM on GPUs 0 and 1. Keep both profiles and
their caches available so switching back is straightforward. Start with
GPU-only caching and the documented model-specific sampling settings, then
run the same client tasks and performance checks. Test caching separately.

**Done when:** we know whether GLM gives better answers or response times for
our tasks, and have recorded whether to keep it as an optional profile or
propose it as the default. A successful startup alone is not enough.

## 5. Try Qwen Flash Next on the third card

Use the [Qwen3.8-Flash-Next one-GPU profile][qwen]. This is a different model
from our Qwen3.8-27B GGUF entries. Its recipe moves some model tables into
host RAM, so budget that memory separately from prompt caching.

Arrange a test window for GPU 2: stop conflicting llama-swap models and
account for the other services using that card. Test Qwen on a separate API
port with its own runtime cache. Keep DeepSeek available on the pair if the
host has enough RAM and storage for both workloads.

Compare Qwen against the existing llama-swap chat model using our prompts.
Check tool calls, reasoning settings, and total answer latency. Restore the
normal GPU 2 services after the experiment.

**Done when:** we know whether the dedicated Qwen server earns its memory
cost and whether it affects the other services. Keep llama-swap available
for its existing model-switching and OCR workloads.

## 6. Record and keep the useful changes

For each accepted change, record the image digest, model revision, settings,
hardware conditions, performance results, failures, and rollback procedure.
Pin benchmark tooling too. Do not use a moving image tag as the rollback.

Put deployment and recovery commands in the owning [vLLM runbook](../roles/vllm/README.md)
or [AI runbook](../roles/ai/README.md), and correct stale hardware notes after
host verification. Keep this document as the ordered plan.

Follow [Contributing validation](../CONTRIBUTING.md#validation) for each
implementation change: `make check`, `git diff --check`, and focused template
rendering with placeholder values where launch behavior changes. Deploy only
within an explicitly authorized host scope using [Operations](operations.md).
This plan does not start a deployment or authorize a driver upgrade.

Keep the prior working images and weights until the replacement has passed
normal use and rollback has been tested. Decide on cleanup separately.

## Upstream references

The model pages and their recorded test conditions take priority over older
generic launch examples. Recheck them when each step starts.

- [Shared image and cache guide][shared]
- [Container releases](https://github.com/local-inference-lab/blackwell-llm-docker/releases)
- [DeepSeek text profile][deepseek]
- [GLM Spark two-GPU profile][glm]
- [Qwen Flash Next profile][qwen]
- [Runtime comparison and its measurement limits][results]
- [Benchmark tool][bench]

[shared]: https://github.com/local-inference-lab/rtx6kpro/blob/master/docs/unified-vllm-docker.md
[deepseek]: https://github.com/local-inference-lab/rtx6kpro/blob/master/models/deepseek-v4-flash.md
[glm]: https://github.com/local-inference-lab/rtx6kpro/blob/master/models/glm-5.3-flash-spark-tp2.md
[qwen]: https://github.com/local-inference-lab/rtx6kpro/blob/master/models/qwen38-flash-next.md
[results]: https://github.com/local-inference-lab/rtx6kpro/blob/master/benchmarks/karmic-kraken-serving.md
[bench]: https://github.com/local-inference-lab/llm-inference-bench
