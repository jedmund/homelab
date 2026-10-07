# max power events, September to October 2026

Host: `max` (`atelier-max`), ASRock WRX90 WS EVO, Threadripper Pro 9955WX,
four 32 GB RDIMMs, three RTX Pro 6000 Blackwell cards, Ubuntu 26.04 with
kernel 7.0.0-38 and NVIDIA 615.71.09. This record covers the unexplained
outages through October 7, 2026, what was ruled out, and the instruments
added to catch the next one. Procedures live in the
[crash capture runbook](../roles/crash_capture/README.md).

## Events

| Time (PDT) | Uptime before | Load at the time | Found in |
| --- | --- | --- | --- |
| Sep 28 11:48 | 7 days | A CI job container had just started | Journal |
| Oct 5 23:21 | 46 hours | A CI run winding down | Journal |
| Oct 6 10:37 | 11 hours | About 98 percent idle | Journal |
| Oct 6 17:33 | 4 hours | About 98 percent idle, no CI or inference | Journal, netconsole, host readings |

Each time the host dropped off the network and stayed down until it was
power-cycled by hand. The persistent journal ends mid-stream with no panic,
lockup, machine check, PCIe error, Xid, or OOM message. pstore, the firmware
boot error table, and the ECC counters were empty.

## October 6, 17:33

This was the first event with instrumentation in place.

- Netconsole on nuc-mini shows routine messages up to 17:33:40 and nothing
  after. The kernel printed no error.
- The last host readings, 25 seconds earlier, were normal: CPU 38C, GPUs
  34-36C, VRM 42C, board 34-36C, DDR5 38-42C, fans normal.
- The host was left half-powered. Every fan ran, the debug display showed
  `00`, and the BMC reported the chassis off with no sensor readings. A BMC
  power-on had no effect.
- The BMC event log had no entry for the event. The BMC watchdog never
  fired, because the BMC treated the host as off.
- Switching off the HX1500i changed nothing visible. Switching off the
  HX1000i stopped the fans. After both were switched back on, the host
  booted normally.

The 24-pin side stayed powered while the board lost power-good. That points
at the CPU's power path rather than at software.

| PSU | Feeds |
| --- | --- |
| Corsair HX1000i | 24-pin motherboard power, RTX Pro 6000 Workstation Edition |
| Corsair HX1500i | CPU EPS, both RTX Pro 6000 Max-Q cards |

## Ruled out or unlikely

- **Heat.** October 3 and 4 reached 91-92F in 94110 without an event. The
  October 5 and 6 events happened at about 58-75F outside, and the 17:33
  readings were cool.
- **Load.** The two most recent events happened at idle. No model loaded or
  unloaded near either one.
- **Memory errors.** ECC counters and rasdaemon show none.
- **Kernel-detected faults.** Nothing was logged, and the BMC recorded no
  CPU thermal trip, PROCHOT, or machine check.

## Changes since September 21

| Date | Change |
| --- | --- |
| Sep 21 | NVIDIA R580 to R615; kernel 6.8 to 7.0 HWE; large CI runner pool added |
| Oct 3 | General CI pool raised to six concurrent jobs |
| Oct 4 | Ubuntu 26.04 upgrade, which removed the 6.8 kernels |
| Oct 7 | Workstation Edition limited from 600 W to 300 W ([GPU host runbook](../roles/gpu_tools/README.md#power-limits)) |

All four events happened after September 21. The only earlier boot in the
journal ended cleanly. The October 7 power limit lowers the HX1000i's peak
load, so it is a new variable when comparing event rates.

## Instruments

- BMC watchdog, lockup and oops panics, kdump, rasdaemon, netconsole to
  nuc-mini, and serial console
  ([crash capture](../roles/crash_capture/README.md)).
- Gatus push endpoints for heartbeat, unexpected reboot, cooling, and
  hardware events ([Gatus](../roles/gatus/README.md#what-it-checks)).
- Both PSUs over USB through the `corsair-psu` driver, logged every 15
  seconds with output power, 12V, temperatures, fan, and each unit's own
  uptime.
- Remote BMC access through an Operator IPMI account; commands need
  `-L OPERATOR`.

The BMC event log had been full since the June 1 rebuild because of a
flapping fan sensor. It was saved, cleared, and the sensor's events turned
off on every boot.

## Open items

- **Next event.** Read the last `psu` line before it. If one unit's uptime
  is shorter than the other's, that PSU dropped out on its own.
- **BIOS Power Supply Idle Control.** Still at its default. Typical Current
  Idle is the standard fix for AMD systems that lose power at very low idle
  current, and is the first change to try if the HX1500i side is implicated.
  It was deferred to capture one more event first.
- **Recovery.** Manual until the planned enterprise UPS with managed outlets:
  switch the HX1000i off for about 60 seconds.
- **Exposure.** About 1,100 packets an hour from public addresses reached max
  on port 11434 (llama-swap). The router forwarding behind this has not been
  checked.
- **Email alerts.** SendGrid rejects Gatus mail ("Maximum credits exceeded");
  Discord is the only working alert path.
- **BMC firmware** is 1.04.00 from January 2024.
