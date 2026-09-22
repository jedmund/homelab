# GLM 5.3 Flash setup — September 21, 2026

The user authorized downloading and setting up GLM and copying the inference
changes into `~/Developer/homelab`. That checkout exists on `max` at
`/home/justin/Developer/homelab`, on branch `main`, initially clean at
`739b182`. The similarly named path does not exist on the local control Mac.

## Configuration

The alternative `glm-5.3-flash-spark` profile uses
`local-inference-lab/GLM-5.3-Flash-NVFP4-Spark` at revision
`a608241037e4c2565356bff7ca293f2133888f88`. Target, code, and MTP revisions
are pinned. The image remains the validated Karmic assembly from the
[DeepSeek runtime update](inference-runtime-upgrade-2026-09-21.md).
The [vLLM runbook](../roles/vllm/README.md#glm-53-flash-spark-alternative)
owns download, switching, and recovery commands.

The exact image's `--print-config` confirmed the dedicated upstream preset:
TP2/DCP2, MTP3, four slots, 3,072 batched tokens, 4,190,109,696 bytes of KV
memory per GPU, auto context length, B12X backends, temperature 1/top-p .95,
and high reasoning. External cache service is disabled. Port 11438 serves
`GLM-5.3-Flash`; GPUs 0 and 1 are shared with the alternative DeepSeek profile.
Both models must not run together. GPU 2 services remain independent.

The installed `hf` 1.15.0 CLI downloads all 58 snapshot files into the existing
HF cache. Upstream metadata reports 187,694,218,158 bytes. The host had 417 GiB
free before download. Existing DeepSeek weights and rollback caches are kept.
The download completed successfully in about 27.5 minutes (175 GiB on disk).
`hf cache verify` checked all 58 files against the pinned revision with
missing/extra-file failures enabled; all checksums matched. GPU serving
validation reached readiness in 521 seconds. The API reports a maximum context
of 950,272 tokens after automatic fitting, with 953,418 shared KV tokens.
This is configured capacity, not a validation of answers near that full limit.

Chat and Python deduplication passed review; strict JSON and required tool
calls passed assertions. LAN access on port 11438 passed. Synthetic 32K and
120K retrieval returned the correct code and completed naturally, in 3.720 and
15.557 seconds respectively.

All six operations handoffs completed naturally and included the code. All
six exceeded the requested 500–700 words (741–792 words). The first reviewed
answer at each context invented completed checks, scheduling or a healthy
state. Median elapsed times were 6.189 seconds at 32K and 6.430 seconds at
120K. Generated lengths were 994–1,102 tokens including reasoning. These
results do not establish a quality improvement over DeepSeek.

Startup used about 88.09 GiB per GPU for model loading. Allocator OOM warnings
occurred during loading, but the runtime recovered and served the tests.
Missing optional Triton-kernel imports and PyTorch deprecations were also
logged. Preserve these observations when comparing later runtime builds.

## Repository preservation

The source worktree and host checkout started at the same revision. Only our
explicit changed/new paths were copied. Each destination was checked against
its original or previously synchronized content to avoid overwriting unrelated
edits. Prior files are backed up outside Git in
`/home/justin/.cache/inference-upgrade/glm-20260921/checkout-before`.

The master playbook imports `ai.yml`, whose default `ai_gpu_mode` is `split`.
It does not import the explicit `ai_split.yml` workflow or `vllm.yml`, so a
normal full deployment does not render or switch vLLM profiles. Future explicit
vLLM renders use the new pinned image and both profiles. The split workflow
still defaults to DeepSeek and stops competing model profiles before startup.
No role pins the old host driver or kernel for reinstallation.

Changes are local working-tree edits in the host checkout; no commit, push, or
merge was requested. The copy does not deploy unrelated stacks.

## Validation and evidence

`make check` passed all playbook syntax checks and lint with zero failures or
warnings. Placeholder rendering and Compose parsing passed for both model
profiles; GLM port, GPU visibility, revision and preset were asserted. Ansible
rendered the combined Compose file on `max` without switching the running
DeepSeek container. One short-context benchmark pass completed all three 30-second windows without
request errors, repetition flags, or underfilled concurrency. Aggregate decode
was 175.6 / 262.4 / 372.6 tokens/s at concurrency 1 / 2 / 4. DeepSeek's three-pass
medians on the same driver/kernel were 194.1 / 275.3 / 401.9. Repeats differ,
models and tokenizers differ, and CI remained active, so this is a limited
comparison. It does not establish a GLM speed advantage.

The benchmark remains pinned to 0.6.2 commit
`ccd9ad8ced7e387794391bfb0ac6d99b1f66ba6f`, with exact token targeting,
4,096-token outputs, temperature 1, loop detection, and DCP2. Short tests use
context zero with prefill skipped. The benchmark's generic metrics calculation
estimated 1,241,088 KV tokens (303 blocks × 2,048 × DCP2), above the runtime's
953,418-token hybrid-cache report. All selected cells require less than the
lower runtime capacity; do not use the generic estimate as the serving limit.
One long-context pass completed all six windows without request errors,
repetition flags, underfilled concurrency, or capacity-limited measurements:

| Prompt tokens | C1 tokens/s | C2 tokens/s | C4 tokens/s |
| --- | ---: | ---: | ---: |
| 32,768 | 169.5 | 265.9 | 381.4 |
| 120,000 | 173.7 | 265.3 | 390.6 |

Fresh-prompt scouts measured 3.735 seconds to first token at 32K and 15.188
seconds at 120K. This is one pass; it does not establish long-term reliability
or quality at the advertised maximum context.

A cached GLM restart reached readiness in 280 seconds. The same 950,272-token
context and 953,418 KV-token capacity were reported. Chat/code review and
JSON/tool assertions passed again. Repeating Compose startup retained the
container ID and start time.

GLM is retained as an optional profile. DeepSeek remains the default because
these samples do not show better speed or handoff quality. DeepSeek was restored
and passed chat/code review, JSON/tool assertions, and LAN model discovery.
GLM is stopped, with its weights and compiler cache retained for switching.
All seven AI side containers remained healthy. Final kernel logs contained no
NVIDIA Xid or host OOM events; the earlier allocator warnings are separate.
Vision inputs, context beyond 120K, and extended interactive use were not tested.

Raw download/checksum logs, launch configuration, synthetic API results,
benchmark results/tooling, restart checks and final host state are archived on
`max` outside the repository:

```text
/home/justin/.cache/inference-upgrade/glm-20260921/glm-setup-20260921.tar.gz
SHA256 0de2a32c9d57707f2d6ae4d2c0407fcf875725b0a432afeb444b5c119d51a230
```

The archive contains a per-file manifest and excludes virtual environments.
Local and remote archive checksums matched. Final source files were synchronized
again to `/home/justin/Developer/homelab` with content-hash verification. Fast
validation and `git diff --check` passed in both working trees. Full Ansible
syntax/lint and focused Compose checks ran in the control worktree; the host
checkout has identical changed files and no unrelated edits were replaced.
