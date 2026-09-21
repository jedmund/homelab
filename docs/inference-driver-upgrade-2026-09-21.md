# Inference host maintenance — September 21, 2026

Host: `max` (`atelier-max`), Ubuntu 24.04.5. This record follows the
[original baseline](inference-baseline-2026-09-21.md) and the
[inference upgrade plan](inference-upgrade-plan.md). The user authorized the
R615 installation and reboot, then separately requested the Ubuntu HWE kernel.
Service procedures and recovery steps are in the
[GPU host runbook](../roles/gpu_tools/README.md).

## Driver installation

Replaced Ubuntu's open R580 server driver, 580.178.04, with NVIDIA's open
615.71.09 driver (`nvidia-open=615.71.09-2ubuntu1`). The signed NVIDIA Ubuntu
24.04 repository is enrolled through
`/etc/apt/sources.list.d/homelab-nvidia-driver.list`, using
`/usr/share/keyrings/homelab-nvidia-driver.gpg`. NVIDIA's matching version
pinning package is installed.

All 40 staged candidate and rollback package checksums passed. After repository
enrollment and pinning, the actual APT simulation matched the reviewed package
transaction. CI was drained with SIGQUIT, GPU workloads stopped, and the staged
packages installed without a general system upgrade or autoremove.

DKMS built R615 for kernels 6.8.0-138 and 6.8.0-139. Package audit was clean,
the boot kernel's module version matched, and its regenerated initramfs retained
the DRM configuration. After reboot, all three GPUs reported R615 with CUDA
13.4 support. GPU identities, 96-GB memory sizes, 300/300/600-W power limits,
DRM modeset/fbdev, and `amd_iommu=pt iommu=pt` arguments were preserved.

## Compatibility issue and recovery

The existing DeepSeek container initially failed with CUDA error 803. A fresh
GPU diagnostic container using the exact same image successfully allocated
a CUDA tensor. Inspection found three stale, generated `00-compat-*.conf`
loader entries in the existing container, selecting its bundled CUDA 13.2
compatibility driver. Moving those entries aside and rebuilding the container's
loader cache restored native driver access and successful startup.

The original container, image digest, model revision, ports, GPU split,
mounts, and inference settings were retained. The runtime/model upgrade has
not started. This loader repair is documented in the owning runbook.

## R615 checks on kernel 6.8

- DeepSeek: chat and Python deduplication answers passed manual review;
  strict JSON and required tool-call assertions passed. All completed naturally.
- Long retrieval: the unchanged synthetic recovery-code test passed at
  approximately 32K and 120K input tokens with natural completion.
- Embeddings: returned a 1,024-element vector with finite values.
- Speech: Kokoro generated a synthetic sentence; GPU Whisper transcribed
  “The local inference server is ready for testing.” correctly.
- llama-swap: the existing `qwen3.6-flash` model returned 42 for 17 + 25 and
  completed naturally. This is an execution check, not a broader quality result.
- Emulator: Vulkan enumerated the NVIDIA Workstation card, and a real EGL/OpenGL
  context reported `NVIDIA RTX PRO 6000 Blackwell Workstation Edition` and
  OpenGL `4.6.0 NVIDIA 615.71.09`. Interactive game streaming was not tested.

Three 30-second passes at each short-context concurrency completed without
request errors or repetition flags. Aggregate generation medians:

| Concurrent requests | R580 + kernel 6.8 | R615 + kernel 6.8 | Change |
| --- | --- | --- | --- |
| 1 | 195.0 tokens/s | 190.9 tokens/s | -2.1% |
| 2 | 287.6 tokens/s | 271.3 tokens/s | -5.7% |
| 4 | 422.4 tokens/s | 414.0 tokens/s | -2.0% |

The same pinned benchmark, image, model, 30-second windows, output cap, and
sampling settings were used. This reduced run omitted prefill and long decode
cells, so its global decode warmup used short context instead of 120K.
GPU 2 had also loaded a chat model for its service check. Treat this as an
approximate comparison, not an isolated driver-performance claim. R615 meets
the new runtime prerequisite; these measurements do not show a speedup.

The original baseline's long-generation repetition failures and unsupported
handoff claims remain unresolved; successful retrieval does not supersede
those quality findings.

## HWE kernel

Installed Ubuntu's `linux-generic-hwe-24.04`, version
`7.0.0-31.31~24.04.1`, from the existing signed Ubuntu repositories.
The reviewed transaction adds seven packages and removes none. Packages are
installed. R615 DKMS built successfully for kernel 7.0.0-31; module,
initramfs, package-audit, and GRUB syntax checks passed. The IOMMU/GRUB
configuration was unchanged, and the new kernel includes the host's i40e
network and NVMe drivers. Existing 6.8 kernels and the GA tracking metapackage
remain available as fallbacks. The second reboot returned on
`7.0.0-31-generic` with all three GPUs on R615, unchanged power/memory
limits, and DRM modeset/fbdev enabled. The root filesystem is mounted
read-write, SSH networking works, and CI has resumed accepting jobs.
After the second reboot, all four DeepSeek API checks and both 32K/120K
retrieval checks passed again. Embeddings, synthetic speech transcription,
llama-swap chat, and NVIDIA EGL/OpenGL checks passed. The runner's configured
registration verified as valid and resumed processing jobs. The CUDA loader
repair survived the restart; no second repair or container recreation was needed.

The single short throughput pass returned 189.7, 282.8, and 417.6 aggregate
tokens/s at concurrency 1, 2, and 4. All three windows passed without request
errors or repetition flags. CI was active during this pass; it is an
operational check, not an isolated comparison of kernel performance.

LAN health checks returned HTTP 200 for DeepSeek, llama-swap, and embeddings.
All 19 containers recorded before maintenance retained their IDs, images, and
running/stopped states; newly launched CI job containers are outside that
comparison. All existing health checks were healthy, no recorded container
reported an OOM, and the new kernel log had no NVIDIA Xid, driver API mismatch,
or GPU-fallen-off-bus messages.

## Evidence and limits

Host evidence, install logs, package manifests, staged rollback packages, and
service-check output are stored outside the repository at
`/home/justin/.cache/inference-upgrade/20260921`. Synthetic inference results
are kept separately from the original R580 baseline. The R615-on-6.8 archive
is `r615-checks-20260921.tar.gz` in that directory; its SHA-256 is
`39130d6c2ece1f32a170a4bb5b018de48cb0991087823b832269b097ff4b1cc6`,
verified locally and on the host. The final kernel-check archive is
`hwe-checks-20260921.tar.gz`, SHA-256
`93a34d7a79b5b7346784aded3d5b65a35b765ded9c3ec1a18f57d9b8a06bc622`,
also verified at both ends.

A full-day soak, interactive clients, game streaming, and actual rollback
remain untested. This maintenance does not establish compatibility or
performance of the proposed Karmic Kraken runtime.

## Repository validation

Only documentation changed in the repository. Fast validation, explicit local
link checks covering the new documents, referenced command/path checks, and
`git diff --check` passed. The host maintenance above was applied directly;
no Ansible behavior or application deployment configuration changed.
