# G965N: SUSFS 2.2.0 + Smooth65 CPU profile

Experimental follow-up to `de865ad15dc4b01bfc838d5b2375c2487011817e`.
For **SM-G965N only**, using the supplied DS-ACK OneUI7 EROFS installer.
This is not a tested universal S9/S9+/Note9 kernel. Keep a known-good boot
backup and working recovery. Do not flash without a recovery path.

## Changes

| Area | Previous behavior | Smooth65 |
| --- | --- | --- |
| Schedutil, both clusters | 5 ms up / 5 ms down | 1 ms up / 20 ms down |
| Frequency work | Shared normal-priority workqueue | Dedicated high-priority, memory-reclaim-capable workqueue |
| Worker CPU selection | Count minus one could name an offline CPU | Select an actual online LITTLE CPU; retain idle preference and panic fallback |
| M3 policy ceiling | DT policy capped at 1,924 MHz | Allow requests up to 2,704 MHz, within the real CAL table and hotplug limits |
| BIG thermal switch-on | DT 55°C, possibly overwritten by ECT | 65°C, applied after ECT |
| LITTLE first limiting band | DT 76°C, possibly overwritten by ECT | 65°C, 2°C hysteresis, applied after ECT |
| LITTLE cold band | ECT could impose a frequency cap even at low temperatures | Cooling state 0, using the real frequency-table maximum |

The intent is quicker response to increasing load and fewer short frequency
drops while scrolling or opening apps. It does not force high clocks while idle,
change the scheduler's placement algorithm, or establish an FPS improvement.
Down-rate delay does not suppress thermal/QoS policy-limit enforcement.

**65°C is CPU sensor temperature, not battery temperature.** It is the point
where the CPU thermal controller can begin limiting power/frequency, not a
guaranteed maximum temperature. BIG retains its PID control target (83°C in the
baseline DT, subject to ECT), calibrated parameters and higher protection trips.
LITTLE retains the existing frequency caps in its higher bands. If ECT supplies
normal trip temperatures below the new start, they are placed in increasing
1°C steps from 65°C; existing higher values are retained. HOT/CRITICAL trip
temperatures are never moved. An unrecognized or conflicting layout is rejected
without a partial profile update and emits a warning; inspect the on-device log.

M3 is **not** set to 2.704 GHz on all four cores. Existing Samsung hotplug limits
remain: up to the supported 2.704 GHz ceiling with one M3 active, 2.314 GHz with
two, and 1.924 GHz with three/four. Both clusters are bounded by their actual
CAL frequency tables; no voltage or OPP is invented. A55 keeps the earlier
2.002 GHz request only if the firmware exposes that level. Battery, power,
hotplug and ROM policies can still reduce the effective maximum below 65°C.

## Unchanged

- Original KernelSU-Next version 33024 and its SUSFS 2.2.0 bridge/module ABI.
- SELinux enforcing defaults, EROFS, GPU clocks/thermal policy, battery/PMIC
  protections, thermal hotplug and emergency shutdown thresholds.
- Suspend/idle, CPU minimum frequencies, voltage tables and hotplug core-count limits.
- RAM, swap, zram/writeback and UFS configuration. This does **not** make the
  phone RAM-only; any existing ROM backing-device/writeback setup still applies.
- Installer, ramdisk scripts, shared G960F base and every other model payload.

Only `floyd/G965N-kernel` and `floyd/G965N-dtb` change in the ZIP. The DTBH is
patched at eight fixed-size property payloads, preserving every other byte,
including its Samsung header, padding, EROFS fstab and idle-IP strings. Its
matching G965N DTS contains exactly those eight property changes. The release
does not use a wholesale decompile/recompile of the original DTB.

## Build and package

Use the original attachment, not the previous SUSFS ZIP, as the delta base.
Original ZIP SHA-256:
`4ad9f321f1710a7e7177040d37dff54e8664a546dd9c89199df03bc00cc15f14`.
Extract the original G965N Image/DTBH by applying each original G965N BSDIFF40
payload to its G960F base. See [SUSFS-G965N.md](SUSFS-G965N.md) for the pinned
KSU submodule, bridge patch, compiler and dependencies.

```sh
export DS_ACK_TOOLCHAIN=/absolute/path/to/clang-20.0.0-r547379
export DS_ACK_LOCALVERSION=-DS-ACK-G965N-KSU-SUSFS220-Smooth65
bash tools/build_g965n_susfs.sh /absolute/path/to/original-G965N-Image
python3 tools/test_g965n_smooth65.py
python3 tools/verify_susfs_abi.py /path/to/susfs4ksu-binaries
python3 tools/tune_g965n_dtb.py original-G965N-dtb smooth65-G965N-dtb
python3 tools/repack_g965n_susfs.py original.zip arch/arm64/boot/Image \
  DS-ACK-G965N-KSU-SUSFS220-Smooth65-Enforcing-TEST.zip --dtb smooth65-G965N-dtb
```

`bsdiff4` is required for packing. The packer verifies the exact baseline,
validates that the optional DTB equals this profile applied to the original,
round-trips both deltas, and rejects changes to unrelated entries. It refuses
to overwrite existing local output files. Build timestamps can change the
Image/ZIP hashes on a rebuild.

## Checks and device verification

Host tests compile the actual thermal-profile, CPU-selector, frequency-rate
and cooling-level functions into a harness with AddressSanitizer/UBSan. They
cover thermal boundaries, preserving emergency trips, rejecting invalid layouts
without mutation, non-CPU zones, ECT early bands, real-table cold-band state 0,
4,096 online/idle mask combinations and rate-limit boundaries. This cannot
validate real hardware, interrupt timing, thermal calibration or workqueue races.
LeakSanitizer is disabled because the fixture allocates no heap and this host
does not expose the task information it needs.

Completed for this artifact on 2026-08-30:

- ARM64 Image build with the pinned Android Clang 20 toolchain and FMP HMAC
  generation completed; release `4.9.337-DS-ACK-G965N-KSU-SUSFS220-Smooth65`.
- Embedded config equals the verified build config; only SUSFS config entries
  differ from the original uploaded Image. The KSU submodule's working diff is
  byte-identical to the already-published SUSFS bridge patch.
- Host profile tests and the existing 12-structure/42-field/15-command SUSFS ABI
  checks passed. Both original and modified DTS compile; their property diff
  consists of exactly the same eight changes found in the packaged DTBH.
- ZIP CRCs, all 24 entry payloads, entry order and preserved metadata verified:
  exactly the two G965N payloads changed; the other 22 did not.
- The original installer's ARM64 patch executable ran under QEMU user mode and
  reconstructed both Image and DTBH byte-for-byte. This does not boot Android.
- ZIP size: 44,468,643 bytes. Image size: 38,044,160 bytes. DTBH: 311,296 bytes.

| Artifact | SHA-256 |
| --- | --- |
| ZIP | `2955320299ba1363a107522856d6f4ad57b40f67bbd9c5bfe91da96903ee4d05` |
| Image | `b369b7bb33c4e81d22a56acc96b480c05e1604eabec8711795342ab223d2c9bc` |
| DTBH | `2f312d0d0571fdb36d5cb70f36df7c8015eb070362fba8517ecd160e79a9687e` |

After a successful boot, check these read-only values from an authorized root
terminal. ROMs can use different thermal-zone numbers, so identify zones by type:

```sh
uname -r
su -c 'dmesg | grep -E "CPU thermal throttling|CPU 65C profile rejected"'
su -c 'for p in /sys/devices/system/cpu/cpufreq/policy*; do
  echo "$p"; cat "$p/scaling_governor" "$p/scaling_available_frequencies" "$p/scaling_max_freq"
  cat "$p/schedutil/up_rate_limit_us" "$p/schedutil/down_rate_limit_us"
done'
su -c 'for z in /sys/class/thermal/thermal_zone*; do
  case "$(cat "$z/type")" in BIG|LITTLE)
    echo "$z"; cat "$z/type" "$z/temp" "$z/trip_point_1_temp";; esac
done'
```

Expected governor: `schedutil`; rate limits: `1000` and `20000` microseconds;
BIG/LITTLE trip 1: `65000` millidegrees; successful CPU-profile log messages.
Unavailable sysfs files or different effective values require investigation,
not disabling thermal protection. Check KSU root and SUSFS version through the
existing module as described in SUSFS-G965N.md.

Start with normal app use; do not stress-test while charging. Compare short
repeatable scrolling/app-launch sessions and idle drain against the known-good
kernel. Stop and restore the backup if there is rebooting, freezes, abnormal
battery heat/drain or broken sleep. Runtime boot, sustained performance, battery
life and reaching the requested clocks remain **unverified** until tested on
the user's G965N.
