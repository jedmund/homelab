# GPU host tools

This role installs `hwsummary` and `gpu-burn`, configures NVIDIA DRM modeset,
and refreshes initramfs images when the modeset configuration is missing.
It does not install or upgrade the NVIDIA driver. It is included by the AI
deployment and has a separate [playbook](../../deploy/gpu_tools.yml).

Preserve the host's `amd_iommu=pt iommu=pt` kernel arguments. The inference
pair depends on the existing PCIe configuration. Emulator containers also
need NVIDIA graphics support and DRM modeset; a compute-only driver package
selection is insufficient for this host.

## R615 maintenance on max

Prepared September 21, 2026 as a prerequisite for the
[inference upgrade](../../docs/inference-upgrade-plan.md). R615 and a separately authorized HWE kernel upgrade were applied.
See the [maintenance record](../../docs/inference-driver-upgrade-2026-09-21.md)
for validation, performance measurements, and limitations.

| Item | Selected value |
| --- | --- |
| Previous driver | Ubuntu `nvidia-driver-580-server-open`, 580.178.04 |
| Installed driver | NVIDIA `nvidia-open`, `615.71.09-2ubuntu1` |
| Package source | NVIDIA's signed Ubuntu 24.04 x86-64 repository |
| Scope | Replace driver and graphics libraries, update DKMS, then reboot `max` |
| Services affected | Inference, embeddings, speech recognition, emulator graphics; the reboot also interrupts CI and other containers |

An isolated APT configuration was used to refresh signed Ubuntu/NVIDIA
metadata and simulate this candidate against the host's installed package
state. The simulation with NVIDIA's version pin succeeded: one upgrade
(DKMS), 22 new packages including `nvidia-driver-pinning-615.71.09`, and 16
removals. All removals are in the old NVIDIA driver/graphics package set,
including `nvidia-prime`. The preflight did not change installed packages or system APT sources.
The actual transaction was checked against that simulation before installation.

The package archive contains 17 rollback packages and 23 candidate packages,
including the version pin. `rollback-packages.json` records the old versions;
`sha256.json` records downloaded file checksums. `simulation-pinned.log`
contains the reviewed package transaction.

At preflight, the boot kernel's headers were installed, Secure Boot was
disabled, and `/boot` had 1.6 GB available. R580 DKMS modules were installed
for kernels 6.8.0-138 and 6.8.0-139.

Follow [NVIDIA's Ubuntu installation guide][nvidia] for repository enrollment
and version pinning. Its newer packages omit the branch number in their
names; do not substitute a guessed `nvidia-driver-615-open` package name.

### Before applying

1. Obtain authorization for the driver change and host reboot. Arrange for
   CI jobs to finish and confirm a recovery path if SSH does not return.
2. Preserve the working inference image, pinned model snapshot, GPU settings,
   and the recorded running/stopped state of each affected service. The
   [baseline record](../../docs/inference-baseline-2026-09-21.md) identifies
   the current inference artifacts.
3. Retain the downloaded old and new packages under
   `/home/justin/.cache/inference-upgrade/20260921`, including their manifest
   and checksums. Verify all required downloads completed before installation.
4. Enroll the official signed repository and pin driver version 615.71.09
   using its matching NVIDIA pinning package. Re-run the package simulation
   with the actual repository and pinning configuration. Review any difference
   from the recorded simulation before applying it.

### Apply and check

Stop affected GPU workloads in the agreed maintenance window, install the
reviewed package set, and verify DKMS built successfully for the boot kernel.
Keep the existing kernel arguments and modeset configuration. Check initramfs
generation before rebooting; do not reboot past a failed driver build.

After reboot, check all three GPUs with `nvidia-smi`, verify driver version
615.71.09 and CUDA 13.4 support, and confirm DRM modeset remains enabled.
Restore the recorded service state and check inference, embeddings, speech,
and emulator graphics. Container health alone does not verify graphics or
model output. Confirm the CI runner is available again.

Run the old DeepSeek profile and repeat its API checks before trying a new
inference image. Measure the old image under the new driver separately so a
driver effect is not attributed to the runtime upgrade.

### Roll back if checks fail

Use the saved package manifest to restore the old driver and DKMS versions.
Disable the new driver pin/repository as needed and review the exact APT
downgrade/removal transaction against the installed state. Do not use a broad
package purge. Retain graphics libraries and rebuild modules/initramfs for
the selected kernel, then reboot and repeat service checks.

Downloaded rollback packages have not been installed as a downgrade test.
They provide recovery inputs; they do not prove that rollback will succeed.

[nvidia]: https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html

## Existing containers after a driver change

An existing CUDA container can retain generated
`/etc/ld.so.conf.d/00-compat-*.conf` entries from earlier NVIDIA runtime starts.
On this host, the old DeepSeek container continued selecting its bundled
CUDA 13.2 compatibility driver after the host upgraded to R615. Startup failed
with CUDA error 803, although a fresh diagnostic container from the exact same
image could allocate a CUDA tensor.

Inspect the generated entries and library resolution before changing the
image or model. For this incident, the three entries containing only
`/usr/local/cuda-13.2/compat` were moved to
`/tmp/r615-stale-compat-conf` inside the existing container, then `ldconfig`
was run there. CUDA allocation succeeded with the host-provided driver.
Do not remove compatibility entries blindly on a host whose driver still
needs them. Container recreation should be through the owning role and
preserve the recorded image, settings, mounts, and volume identities.

## HWE kernel maintenance on max

[Ubuntu 24.04 offers a hardware-enablement kernel](https://ubuntu.com/kernel/lifecycle) through
`linux-generic-hwe-24.04`. The September 21 candidate is
`7.0.0-31.31~24.04.1`. The user authorized this as a separate change after
R615 service checks. Keep `linux-generic` and the installed 6.8 kernels as
fallbacks; do not run autoremove as part of this maintenance.

1. Record the current boot ID, kernel, GPU state, and running services. Drain
   CI with SIGQUIT and wait for active jobs to finish before rebooting.
2. Review `apt-get --simulate --no-install-recommends install
   linux-generic-hwe-24.04=7.0.0-31.31~24.04.1`. Install the reviewed packages.
3. Check DKMS and `modinfo -k 7.0.0-31-generic -F version nvidia`. Require
   R615 modules for the new kernel, a completed initramfs containing the DRM
   configuration, and GRUB entries for both the new and fallback kernels.
   Preserve the existing IOMMU arguments. Do not reboot past build failures.
4. Reboot, check `uname -r`, all three GPUs, DRM modeset, network and storage,
   then restore services and repeat actual inference, embedding, speech,
   and graphics checks. Confirm the runner is registered again.
5. If checks fail, select `6.8.0-139-generic` under GRUB's advanced Ubuntu
   menu using the host console and repeat service checks. Retaining the old
   kernel is a recovery option, not a tested rollback.

HWE is a tracking metapackage: future normal package updates can advance its
kernel. The exact version above records this maintenance, not a permanent hold.
