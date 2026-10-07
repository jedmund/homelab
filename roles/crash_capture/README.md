# Crash capture

See the [incident record](../../docs/max-power-events-2026-10.md) for the
events, evidence, and open items.

`max` froze three times between September 28 and October 6, 2026 with no
kernel message, journal entry, ECC error, firmware error record, or pstore
record. The journal ends mid-stream each time. This role adds the layers
needed to record the next freeze. It does not fix the freeze.

Deploy with `make -C deploy crash_capture`. The playbook configures the
netconsole receiver on the `netconsole_receiver` host (nuc-mini) first, then
the `crash_capture` hosts (max). The role never reboots.

## Layers

| Layer | Catches | Active |
| --- | --- | --- |
| BMC watchdog (`ipmi_watchdog`, systemd `RuntimeWatchdogSec=2min`) | Any stop of the kernel or PID 1. The BMC hard-resets the host and logs a watchdog event. | Immediately |
| Lockup and oops panics (`/etc/sysctl.d/90-crash-capture.conf`) | Soft and hard lockups and oopses that the kernel detects; each becomes a panic with all-CPU backtraces | Immediately |
| kdump (`kdump-tools`, `crashkernel=` from its GRUB drop-in) | A vmcore of kernel memory after any panic, in `/var/crash` | Next boot |
| rasdaemon | MCE, PCIe AER, and memory controller errors, stored in its SQLite database across reboots | Immediately |
| Netconsole to nuc-mini | Kernel messages at warning and above, sent over UDP as they are printed | Immediately |
| Serial console on ttyS0 and ttyS1 | The same messages on the BMC's serial-over-LAN, even if the NIC is gone | Next boot |

The kernel arguments are appended through `/etc/default/grub.d/90-crash-capture.cfg`.
`/etc/default/grub` remains hand managed; see the
[GPU host runbook](../gpu_tools/README.md).

The firmware publishes no SPCR table, so the role does not know which UART
the BMC's serial-over-LAN is wired to and uses both. Serial-over-LAN only
records while a session is attached; nothing records it continuously yet.

Lockup panics depend on the kernel noticing the lockup. A freeze that stops
every CPU, or a hardware fault below the kernel, still ends in a watchdog
reset with no panic. The watchdog event and the absence of any netconsole
output then narrow the cause to hardware or firmware.

During kdump, `ipmi_watchdog` extends the BMC timer to 255 seconds. A dump
that takes longer is reset before it finishes. With `-d 31` filtering, only
kernel memory is written.

## Gatus reports

`host-health-report`, run by systemd, pushes four Gatus external endpoints.
The Gatus side, with alert thresholds, is in the
[Gatus runbook](../gatus/README.md#what-it-checks).

| Check | Run | Pushes failure when |
| --- | --- | --- |
| `heartbeat` | Every 2 minutes | Never; Gatus fails it when pushes stop for 10 minutes |
| `unexpected-reboot` | Once per boot (`host-health-boot.service`) | The previous boot's journal does not end with a clean shutdown |
| `cooling` | Every 2 minutes | A sensor in `crash_capture_sensor_limits` is out of range, a BMC threshold sensor is critical, a GPU is at `crash_capture_gpu_max_temp` or reports thermal slowdown or power brake, or an NVMe drive is at `crash_capture_nvme_max_temp` |
| `hardware-events` | Every 2 minutes | A new BMC event log entry not in `crash_capture_sel_ignore`, a new rasdaemon record, or the BMC event log at `crash_capture_sel_full_percent` |

An unclean reboot is classified in the pushed error:

- **Kernel panic captured by kdump**: a new directory under `/var/crash`.
- **BMC watchdog reset (kernel stopped)**: a watchdog entry in the BMC event
  log and no crash dump.
- **No watchdog reset or crash dump recorded**: power loss, a manual reset, or
  a freeze the watchdog did not catch.

The error also carries BMC events since the previous boot started and the
last sensor readings logged before it ended. Every report run logs a
`readings` line, so `journalctl -b -1 -t host-health` shows temperatures and
fan speeds up to the freeze.

Both Corsair PSUs are connected over USB through an internal hub and read with
the kernel's `corsair-psu` driver. Every 15 seconds `host-health-psu.timer`
logs a `psu` line per unit with output power, 12V voltage and current, both
temperatures, fan speed, and the PSU's own uptime. A unit's uptime restarts
whenever that PSU switches on, so after a power event the last `psu` line
before it, which the boot report includes, shows whether one PSU dropped out
on its own. The cooling check also applies `crash_capture_sensor_limits` to
these readings, named `<model>_<reading>` (for example `HX1500i_vrm`).

| PSU | Feeds |
| --- | --- |
| HX1000i | 24-pin motherboard power and the 600 W RTX Pro 6000 Workstation |
| HX1500i | CPU EPS and both 300 W Max-Q cards |

Beszel also graphs the PSU temperatures, because its agent reads every hwmon
sensor. Both units report the same sensor names, so Beszel suffixes the
second (`corsairpsu_vrm_temp`, `corsairpsu_vrm_temp_<n>`) in USB enumeration
order, which can change between boots. Use the model-labelled `psu` lines to
tell the units apart.

The journal is capped at `crash_capture_journal_max_use` (8 GB) rather than
the default, so several weeks of boots stay available for comparison.

A source that cannot be read, such as a failed BMC query, is logged and not
pushed, so it never alerts as a hardware fault. The reboot endpoint is
re-armed by the next report run, so a second unexpected reboot alerts again.

Test without pushing:

```sh
sudo host-health-report boot --dry-run
sudo host-health-report report --dry-run
```

## After the next freeze

The host should reset itself within about two minutes, and Gatus alerts on
`max unexpected reboot`. Open that endpoint on the status page for the
classification, then collect, in this order:

1. BMC event log: `sudo ipmitool sel elist | tail -30` on max. A
   `Watchdog 2` entry with `Hard reset` means the kernel stopped. Also check
   `sudo ipmitool chassis status` for the last power event.
2. Netconsole: `/var/log/netconsole/192.168.1.100.log` on nuc-mini. The
   last lines before the gap are the kernel's final output.
3. Crash dumps: `ls /var/crash` on max. A timestamped directory with
   `dmesg.*` and `dump.*` means a panic was captured; read `dmesg.*` first.
4. Hardware errors: `sudo ras-mc-ctl --summary` and `sudo ras-mc-ctl --errors`.
5. Journal of the previous boot: `journalctl -b -1 -n 200`.

## BMC event log

The BMC event log holds 3,639 entries and stops recording when full. The
`CHA_FAN1/WP` header reads 0 RPM at idle and crossed its 200 RPM lower
threshold every few seconds, which filled the log within minutes of the
June 1, 2026 rebuild. Nothing was recorded from then until October 6.

Lowering the threshold to 0 does not stop the events: this BMC treats a
reading equal to the threshold as crossing it. The role instead disables
event messages for each sensor in `crash_capture_bmc_quiet_sensors` (IPMI
Set Sensor Event Enable). The sensor still reports readings and shows
`Event Messages Disabled` in `ipmitool sensor get`. The role also warns when
the log is more than `crash_capture_bmc_sel_warn_percent` full. Clearing the
log is a manual step:

```sh
sudo ipmitool sel elist > ~/bmc-sel-$(date +%F).txt
sudo ipmitool sel clear
```

## Verify

```sh
sudo ipmitool mc watchdog get    # Timer running, action Hard Reset
systemctl show -p RuntimeWatchdogUSec
sysctl kernel.softlockup_panic kernel.hardlockup_panic kernel.panic_on_oops
systemctl is-active rasdaemon netconsole
cat /sys/kernel/config/netconsole/crash_capture/enabled
sudo kdump-config show           # After a reboot: ready to kdump
```

To send a test message, run `echo "<4>netconsole test" | sudo tee /dev/kmsg`
on max, then check the log on nuc-mini.
