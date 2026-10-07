# Crash capture

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

## After the next freeze

The host should reset itself within about two minutes. Then collect, in this
order:

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
