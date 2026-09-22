# Qwen Flash Next experiment — September 21, 2026

The user chose to proceed with the Qwen experiment, deferring the interactive
client/stability acceptance checks and the old-runtime rollback drill.
The experiment targets GPU 2 on `max`, keeping DeepSeek on GPUs 0 and 1.
Procedures are in the [vLLM runbook](../roles/vllm/README.md#qwen-flash-next-on-gpu-2).

## Configuration and preparation

The checkpoint is `local-inference-lab/Qwen3.8-Flash-Next-NVFP4`, revision
`7c4f1bc1a2d6847e0cbc01ac6b823f00251de8dd`. Target, code and MTP revisions
are pinned. The existing Karmic image digest is retained. The exact image's
`--print-config` confirmed TP1/DCP1, MTP3, CPU PLE tables, and no external cache
service. This experiment explicitly selects text-only mode, four request slots,
and .90 GPU memory utilization. The profile supplies a 262,144-token context
limit and a 6,019-token prefill budget; measured capacity is recorded below.

The service/profile is `qwen3.8-flash-next`, port 11439, API model name
`Qwen3.8-Flash-Next`. It has a separate compiler cache. PLE tables consume
host RAM independently of prompt caching. At inspection the host had 104 GiB
available RAM, GPU 2 used 2,448 MiB, and disk free space was 256 GiB.

The installed `hf` CLI downloads the pinned snapshot into the shared HF cache.
Metadata lists 50 files totaling 105,895,996,845 bytes. The download was
paused at the user's request, then resumed from retained cache files. It
completed, and `hf cache verify` verified all 50 checksums with missing and
extra files treated as failures. Candidate evaluation is recorded below.

## Existing llama-swap comparison

The comparison model is `qwen3.6-flash`, the existing Qwen3.6 35B/A3B
UD-Q8_K_XL GGUF on GPU 2. Chat and Python deduplication passed review; strict
JSON and a required tool call passed assertions. The first chat took 23.394
seconds including on-demand model startup, so it is not a warm latency result.

Synthetic retrieval passed at 16K and 24K, in 2.396 and 4.685 seconds. The
llama-swap tokenizer is accessed through the model's `/upstream/...` proxy,
using `/apply-template` then `/tokenize`; the root `/tokenize` endpoint returns
404. The lower comparison contexts leave room for output within the existing
llama.cpp per-slot context allocation.

All six handoff requests completed naturally and included the recovery code.
The three 16K answers had 778 words, exceeding the 500–700-word requirement;
the three 24K answers had 698 words. Reviewed answers at both lengths invented
completed measurements and healthy system state. These remain quality failures.

One short-context benchmark pass measured 331.6 / 469.6 / 553.0 aggregate
tokens/s at concurrency 1 / 2 / 4. All three 30-second windows completed without
request errors, repetition flags, or underfilled concurrency. The pinned
benchmark is 0.6.2 commit `ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f`, with
4,096-token output windows, temperature 1, prefill skipped, and loop detection.
It used streaming usage counts because llama-swap does not expose the
engine metrics endpoint. The model download ran during baseline measurements;
these are limited samples, not an isolated performance study.

## Deployment integration

Normal AI deployments inspect and stop the GPU 2 experiment before starting
llama-swap. The split-pair workflow accepts DeepSeek and GLM, and rejects Qwen
before deploying any services. Qwen uses its manual GPU 2 workflow so it can
coexist with DeepSeek while llama-swap is stopped.

`make check` passed syntax/lint with zero failures or warnings. A placeholder
three-profile Compose render and exact-image Qwen launch assertions passed.
The AI guard passed when the experiment container was absent. Local execution
of the split preflight accepted both pair profiles and rejected Qwen as
expected. The actual guard tasks stopped a disposable running container and
made no changes on a second run. After the initial candidate crash, the
exited-container path also skipped stopping it. Final restoration is recorded
with the candidate results below.

## Candidate observations

First readiness took 630.2 seconds, including weight loading, compilation,
and warmup. The runtime reported 26.82 GiB of mapped host memory for PLE
and 369,715 shared KV tokens. The API advertises 262,144 tokens per request;
four request slots do not provide four full-size contexts simultaneously.
The generic benchmark's KV estimate does not match this hybrid model's startup
report and must not be used as its capacity measurement.

Chat and Python deduplication passed review. Strict JSON and the required tool
call passed assertions. Retrieval passed at 16K and 24K in 1.409 and 1.653
seconds. All six handoff responses completed naturally, included TULIP-47,
and stayed within 500–700 words (543–667 words). They still overstated
inspection scheduling as completed; one 24K answer also inferred suitable
capacity and a stable environment without evidence. These are quality failures.
The repeated requests used the same seed, not independent randomized trials.

During these checks, GPU 2 used 91,331 MiB and available host RAM was 76 GiB.
TEI produced a 1,024-dimensional embedding, Whisper and DeepSeek health checks
returned HTTP 200, and side-service container identities/start times were
unchanged. This did not exercise audio transcription, TTS, or emulator gameplay.

The first 120K retrieval request overlapped the short benchmark because the
benchmark process had not finished. The engine then crashed with CUDA illegal
memory access, reported in the B12X/GDN attention metadata copy path. The
asynchronous traceback does not establish the originating kernel. All initial
candidate throughput cells are invalid and excluded. The isolated rerun below
passed both workloads separately. This narrows the failure to the earlier
combined workload/state; it does not establish a root
cause or show that concurrent long prompts are safe.

## Upstream issue and deferred investigation

As checked on September 21, 2026, [B12X issue #399](https://github.com/local-inference-lab/b12x/issues/399)
reports the same Qwen3.8-Flash-Next-NVFP4 checkpoint starting and serving
successfully before a CUDA illegal-memory-access failure in the B12X GDN
prefill path during CUDA graph replay. The issue is open, with no comments,
documented fix, or confirmed workaround at the time of review.

The report uses GB10 hardware and a different software environment. Our error
surfaced in a metadata copy operation, and CUDA errors can be reported
asynchronously. The upstream report is a related failure, not confirmation
of the same root cause. Earlier [GDN graph-buffer work](https://github.com/local-inference-lab/vllm/pull/668)
addresses another defect; it is not a verified fix for this local failure.

The local error was illegal memory access rather than an out-of-memory
exception. A pre-crash sample showed 91,331 MiB used out of 97,887 MiB,
leaving about 6.4 GiB free; this sample does not establish memory use at the
instant of failure or rule out transient pressure. Additional VRAM has not
been established as the remedy.

Further Qwen troubleshooting is deferred at the user's request. Retain the
download and manual profile, keep Qwen stopped, and continue using llama-swap
on GPU 2. Single-request limits, disabling MTP, and eager execution were
discussed as diagnostic options but have not been tested as workarounds.
Revisit when upstream provides a relevant fix or a separate investigation
is requested; this issue does not block other inference work.

## Isolated comparison and decision

A cached restart became ready in 290.0 seconds. The benchmark ran alone, then
scheduler metrics confirmed zero running and waiting requests before a separate
120K retrieval check. The 120K check passed in 9.800 seconds. No comparison
request overlapped this benchmark.

| Short decode concurrency | Existing Qwen3.6 llama-swap | Qwen Flash Next |
| --- | ---: | ---: |
| 1 | 331.6 tokens/s | 177.7 tokens/s |
| 2 | 469.6 tokens/s | 302.9 tokens/s |
| 4 | 553.0 tokens/s | 468.0 tokens/s |

These are aggregate output rates from streaming usage counts, one 30-second
window per cell. All isolated candidate cells had zero errors, no repetition
flags, no underfilled concurrency, and no failure reason. The models and
tokenizers differ, and the baseline had the download running. This is a small
comparison, not a general quality or performance ranking. The initially
contaminated run is retained as failure evidence and excluded from this table.

Keep Qwen downloaded and configured as a manual experimental profile; retain
llama-swap for normal GPU 2 use. Qwen passed API and isolated long-context
checks and followed handoff length constraints better, but it was slower on
short decode, still made unsupported claims, occupied most of GPU 2 plus
26.82 GiB of host RAM, and crashed during the combined workload. Do not promote
it to the default. Concurrent long-context qualification and root-cause
investigation remain open; the full 262K limit was not exercised.

The actual AI guard stopped the running Qwen container after the isolated run.
llama-swap was restarted and its `qwen3.6-flash` model returned the expected
response. DeepSeek and the side-service container identities/start times were
unchanged, health checks passed, and embeddings still worked. Qwen and GLM
remain stopped. No host reboot or GPU reset was needed.

## Repository and evidence

The nine Qwen configuration/documentation paths were copied into
`max:~/Developer/homelab` with content-hash verification, preserving existing
edits and saving prior contents under
`~/.cache/inference-upgrade/qwen-20260921/checkout-before`. This includes the
AI stop guard and split-profile preflight. The vLLM Compose file was rendered
on `max`; the normal full playbook was not deployed.

The Qwen changes are reviewed separately from the runtime/GLM work in PR 278.
Raw download,
checksum, API, benchmark, failure, guard, and restoration evidence is retained
under `~/.cache/inference-upgrade/qwen-20260921` on `max`. The local test harness
and results are archived there as `qwen-evidence.tar.gz`, with a SHA-256 sidecar.
No generated deployment files or raw test logs were added to Git.
