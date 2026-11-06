# DeepSeek runtime upgrade — September 21, 2026

Host: `max`, Ubuntu 24.04.5, kernel 7.0.0-31, NVIDIA 615.71.09. The user
authorized updating the runtime after the [driver/kernel maintenance](inference-driver-upgrade-2026-09-21.md).
Deployment and recovery procedures are in the [vLLM runbook](../roles/vllm/README.md).

## Selected candidate

Karmic Kraken beta assembly `20260920-22f3f98b065ed8de`, published September 20
at 23:17 UTC. The registry's `karmic-kraken-beta` channel resolved to the same
image when inspected. The repository pins:

```text
ghcr.io/local-inference-lab/vllm@sha256:60dc178fe69015eb289db12b6183b8d6aec75613e0c659ce7e1f9ba05e8bbed1
```

The [release record](https://github.com/local-inference-lab/blackwell-llm-docker/releases/tag/karmic-kraken-beta-22f3f98b065ed8de60e78c8786ae2bc1b3956616f84b6e148e6393e95251f0bc)
records vLLM `22476af54c637cbb7c7d8193addd160da83a5ce3` and B12X
`f6d8b8eb94cdeb4e652652f925a494c6fc86f101`. This assembly has no recorded
vLLM/B12X changes from the preceding fc3922 build. That preceding build
included separation of CUDA graph cache identities by speculative method and
draft depth. The release is a pre-release; its package/GPU smoke checks do
not qualify whole-model serving performance.

## Preserved deployment contract

- Same `deepseek-v4-flash-0731` service/profile and `vllm` Compose project.
- Same DeepSeek 0731 checkpoint/code revision
  `9e165c30e2704aec5d9d593cce3eebd58bbef1cb`, including the DSpark draft.
- Same `DeepSeek-V4-Flash` API name and published port 11437.
- Same Max-Q GPU pair, TP2/DCP1, host IPC, and GPU visibility.
- Four request slots, 131,072-token limit, and .975 GPU fraction.
- Initial comparison retained 8,192 batched tokens; the deployed configuration uses
  the upstream profile's 4,096-token prefill budget to recover KV headroom.
- Temperature 1/top-p 1 server defaults and thinking/high reasoning.
- Existing model download and prior image/cache retained; no host power or clock changes.

The new profile uses the unified image entrypoint and native argument array.
It receives a separate compiler/runtime cache at
`/opt/docker/vllm/cache/ds4-karmic-22f3f98b`. External caching is explicitly
set to `vram`; both inspected configurations reported no cache service.

Effective configuration was inspected with the exact downloaded image and
rendered environment/arguments using `--print-config` without GPU allocation.
The K5 launch has graph cap 24. The target-only diagnostic uses mode `off`,
zero draft tokens, and graph cap 16. Positive draft tokens are rejected in
off mode, so the temporary command override explicitly sets both controls.

## Rollback and validation

The old working Compose file was saved on the host with the r15 image pinned
by digest, and Compose validation passed. Location:
`/home/justin/.cache/inference-upgrade/20260921/vllm-r15-rollback.compose.yaml`.
The saved file uses the old `ds4-v20-r15` cache and existing model snapshot.

`make check` passed: all playbook syntax checks and lint, with no warnings.
Targeted Ansible renders covered the current profile and the optional legacy
entrypoint/host-network branches; Docker Compose parsing and contract checks
passed. Local Ansible scratch and SSH control paths were placed in writable
task directories after default home-directory writes were rejected by the
workspace sandbox.

`make deploy-vllm` then rendered the new configuration on `max` without
starting it. After pulling and inspecting the pinned image, the old service
was stopped and the target-only candidate started using a temporary Compose
command override. Target-only cold startup took about 359 seconds. Chat and
Python deduplication answers passed review; strict JSON and required tool-call
assertions passed, with natural completion for all four requests.

The server selected DeepGEMM FP8 dense kernels and B12X MXFP4/MXFP8 MoE. It
reported 273,986 shared KV tokens in target-only mode. Startup logged missing
`triton_kernels.matmul_ogs` imports and Qwen video-processor documentation
errors, but the selected DeepSeek backend continued and served all tests.
Both target-only and K5 graph configuration fell back to
`FULL_DECODE_ONLY`; measured performance must reflect this actual behavior.

The initial K5 configuration with an 8,192-token prefill budget reached
readiness and passed all four API checks and both synthetic
32K/120K retrieval checks. It reports 140,855 shared KV tokens, about 8.6%
below the old r15 capacity of 154,127. The target-only capacity above does
not describe normal K5 serving. Under the benchmark's conservative budget,
four independent 32K inputs with 4,096 generated tokens each no longer fit;
keep this capacity regression visible alongside throughput results.

All six operations-handoff requests completed naturally and contained the
recovery code. Their answers had 514–682 whitespace-delimited words, within
the requested range. Median elapsed times were 13.584 seconds at 32K and
7.634 seconds at 120K, versus the original baseline's 5.798 and 6.694 seconds.
The 32K requests generated 2,696–6,932 tokens including reasoning, compared
with 967–1,126 tokens across the old handoff baseline. These are repeated
prefix-cache requests and are sensitive to sampled answer/reasoning length.
They demonstrate slower completion on this task, even if decode throughput
is similar. The first reviewed answer at each context still made unsupported
claims about completed checks/scheduling or a current healthy state. This
quality finding remains unresolved.

The initial 8,192-budget short test completed all nine windows without
request errors or repetition flags. Median aggregate throughput was
188.9/263.3/396.6 tokens/s at concurrency 1/2/4. Its long stress run was
interrupted during preparation to test a smaller prefill budget; it has no
completed long-stress result to report.

## Deployed 4,096-token prefill budget

The upstream-recommended 4,096-token prefill budget limits work per scheduler
batch while preserving the client context and request-slot limits. It reports
338,122 shared KV tokens, 2.19 times the old r15 capacity and sufficient for
four independent 32K inputs or two 120K inputs with the benchmark's 4,096-token
output allowance. Four simultaneous full-size contexts still do not fit.
The profile's healthcheck startup allowance is ten minutes, based on the
roughly 7.5-minute first K5 startup. HTTP readiness, interval, timeout, and
retry checks remain required.

Chat and Python deduplication passed review; strict JSON and required tool-call
assertions passed. Synthetic 32K and 120K retrieval passed. All six operations
handoffs completed naturally and included the recovery code. Five met the
500–700-word request; the final 120K answer had 785 words. The first reviewed
answer at each context still invented completed checks or scheduling, with
unsupported claims about acceptable storage or documented thresholds. These
remain quality failures despite successful API completion.

Handoff median elapsed times were 6.454 seconds at 32K and 7.545 seconds at
120K, compared with 5.798 and 6.694 seconds in the original baseline. Generated
lengths ranged from 1,110 to 2,853 tokens, including reasoning. These sampled,
repeated-prefix requests do not establish a general speed improvement.
Three short-context passes completed all nine windows without request errors,
repetition flags, or underfilled concurrency. Median aggregate decode:

| Runtime and host state | C1 tokens/s | C2 tokens/s | C4 tokens/s |
| --- | ---: | ---: | ---: |
| r15, original R580/kernel 6.8, three-pass median | 195.0 | 287.6 | 422.4 |
| r15, R615/kernel 7.0, one pass | 189.7 | 282.8 | 417.6 |
| Karmic K5/4096, R615/kernel 7.0, three-pass median | 194.1 | 275.3 | 401.9 |

The closest host-state comparison is approximately +2.4% / −2.7% / −3.7%,
but repeats differ and CI jobs remained active. This is not evidence of a
broad decode-speed gain. Tests use pinned benchmark 0.6.2 commit
`ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f`, 30-second windows, 4,096-token
outputs, temperature 1, exact token targeting, loop detection, and no hardware
monitor. Short tests use context zero and skip prefill; their global warmup
also uses context zero.

One long-context pass completed five runnable windows without request errors,
repetition flags, underfilled concurrency, or capacity-limited measurements:

| Prompt tokens | C1 tokens/s | C2 tokens/s | C4 tokens/s |
| --- | ---: | ---: | ---: |
| 32,768 | 193.5 | 287.1 | 417.1 |
| 120,000 | 183.2 | 279.0 | Skipped: KV capacity |

Fresh-prompt prefill scouts measured 3.171 seconds to first token at 32K and
13.424 seconds at 120K, versus original R580/r15 three-pass medians of 3.108
and 12.790 seconds. The new long test has one pass, not the baseline's three;
passing it does not establish that the baseline's intermittent repetition
failure is eliminated.

The 4,096-budget deployment reached application readiness in about 220 seconds.
A subsequent cached restart reached HTTP readiness in 208 seconds including
restart overhead. KV capacity remained 338,122. Chat/code review and strict
JSON/tool assertions passed again. Repeating Compose startup retained both the
container ID and start time.

Final host checks confirmed the pinned image, checkpoint arguments, GPU pair,
context/request limits, API model name, and healthy state. LAN `/health` and
`/v1/models` requests succeeded on port 11437. The other AI containers remained
healthy and kernel logs contained no NVIDIA Xid or OOM events. CI continued
running throughout; no other services were stopped for this runtime change.

The updated runtime remains deployed on `max`. Longer normal-use observation,
interactive agent-client workflows, and an actual rollback drill remain
untested. The saved r15 image/configuration/cache are retained. Do not describe
this upgrade as fixing model quality or proving general throughput gains.

## Evidence

Raw launch configurations, synthetic test results, benchmark source/commit,
validation logs, and final host checks are archived on `max` at:

```text
/home/justin/.cache/inference-upgrade/20260921/karmic-runtime-20260921.tar.gz
SHA256 c222662c258468692a007d981bce17c549bc26d99e06564cad912180e777624b
```

The archive includes a file manifest; local and remote archive hashes matched.
It excludes virtual environments and remains outside the repository.
Individual host logs and the pinned rollback Compose file also remain in that
directory. Local working evidence is under `/tmp/homelab-karmic-20260921`. Preserve the [original baseline](inference-baseline-2026-09-21.md)'s
long-generation repetition failures and unsupported handoff claims when
comparing the new runtime.
