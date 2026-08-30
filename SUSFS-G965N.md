# G965N: restored KernelSU + SUSFS 2.2.0

Experimental integration for the supplied DS-ACK G965N build. Compilation and
host-side checks do not establish that the phone boots or that every feature
works on-device. Keep a known-good boot backup and working recovery before testing.

## Provenance and scope

- Baseline: HaloT455/exynos9810-kernel `463da2717773eeabda7cdcdbf45769716c3aece3`
  (`agent/g965n-ksu-original-a55-20260830`).
- SUSFS donor: Redminote11tech/exynos9810-kernel
  `44883616c0e0ebf4b7432022748e6779bb6185ee`, SUSFS `v2.2.0`, `NON-GKI`.
- Original KernelSU-Next remains pinned at
  `1ce19e536de730829b62d0d23dbd96c6ec809e2f`; kernel version code **33024**.
  The donor's differently structured KernelSU implementation is NOT substituted.
- KSU modifications are stored in `patches/kernelsu-original-susfs220.patch`;
  the build script applies it to the pinned submodule. A plain submodule checkout
  without this patch is not the integrated source.
- ZIP baseline SHA-256:
  `4ad9f321f1710a7e7177040d37dff54e8664a546dd9c89199df03bc00cc15f14`.
- Only `floyd/G965N-kernel` is replaced. The shared G960F base, all DTBs, all other
  model kernels, installer, and ramdisk material remain unchanged.
- Configuration is extracted from the supplied G965N Image. Only
  `CONFIG_KSU_SUSFS*` entries are added; SELinux enforcing defaults, EROFS, and
  existing CPU/GPU/thermal settings remain intact. As in the baseline build,
  the G965N machine define is passed through the build environment, while the
  embedded config retains `CONFIG_MACH_EXYNOS9810_NONE=y`.

## KSU control integration

The bridge accepts the userspace reboot ABI with magic words `0xDEADBEEF` and
`0xFAFAFAFA` only from UID 0. It dispatches 15 commands covering path/path-loop,
mount hiding, kstat add/update, uname, logging, cmdline, open redirect, map hiding,
AVC-log spoofing, and version/variant/feature queries. Existing KSU manager
installation, ioctl/supercall interface, root authorization, and native per-app
unmount remain in place.

SUSFS initialization, post-boot monitoring, SID lookup, and per-app hiding flags
are wired into original KSU lifecycle hooks. The bridge uses original KSU's
`u:r:su:s0` domain, not the donor's `u:r:ksu:s0`. KSU's per-app unmount choice
determines which zygote children receive SUSFS hiding flags.

Enabled: SUS_PATH, SUS_MOUNT, SUS_KSTAT, SPOOF_UNAME, ENABLE_LOG,
HIDE_KSU_SUSFS_SYMBOLS, SPOOF_CMDLINE_OR_BOOTCONFIG, OPEN_REDIRECT, SUS_MAP.
The donor does not implement the declared TRY_UMOUNT/SUS_MEMFD APIs, so they are
not advertised. Original KSU native unmount is retained. No obsolete SUS_SU hook
or second reboot hook is introduced.

Focused donor corrections include pathname termination checks; the ctime mask;
kstat ABI field width; inode hash collision checks; dentry/SRCU lifetimes;
mount-ID ownership; failed-allocation cleanup; mmap locking and pagemap offsets;
smaps-rollup completion; readlink return lengths; and serialized cmdline updates.
Open redirect resolves the replacement before the one normal open operation,
avoiding the donor's double `do_last()` on an already-open `struct file`.

## Build and checks

Requirements: Android Clang `20.0.0-r547379` (13174946), GNU make, bc, cpio, perl,
Python 3, tar, xz, and an LP64 host C compiler for ABI checks. The submodule needs
full history and tags so its version calculation remains 33024. No credentials
are embedded. The WireGuard network updater is disabled only during this build
to preserve the checked-out baseline source.

```sh
git submodule update --init KernelSU-Next
# If the submodule was cloned shallowly, unshallow it and fetch its tags first.
export DS_ACK_TOOLCHAIN=/absolute/path/to/clang-20.0.0-r547379
bash tools/build_g965n_susfs.sh /absolute/path/to/original-G965N-Image
python3 tools/verify_susfs_abi.py /path/to/susfs4ksu-binaries
python3 tools/repack_g965n_susfs.py original.zip arch/arm64/boot/Image output.zip
```

The repacker needs `bsdiff4`, verifies the exact original ZIP, reconstructs the
new delta, checks CRCs and metadata, and rejects any changed entry besides
`floyd/G965N-kernel`. Extract the original G965N Image by applying the original
`floyd/G965N-kernel` BSDIFF40 delta to `floyd/G960F-kernel`.

Host verification completed:

- Full ARM64 `Image` build and FMP HMAC generation; required SUSFS/KSU bridge
  symbols exist in the linked `vmlinux`.
- 12 userspace ABI structures, 42 field offsets/sizes, and 15 command numbers.
- Root-only dispatch, initialization and post-boot hook presence.
- Universal userspace tool recognizes `v2.2.0` using its current 2.1+ ABI bucket.
  Tested source: sidex15/susfs4ksu-binaries
  `b178f4ec5b2e26cd1b25df34d6aec8ece94b18f9` (`universal-binary`).
- Built Image SHA-256:
  `592350c536531b558a59044f3ea29483297d85bebae363c085fc3a3737957204`.
- Final ZIP: 24 entries verified; only `floyd/G965N-kernel` differs. All DTBs
  and other model kernels are byte-identical to the original.
- The installer's original ARM64 patch executable was run under QEMU user mode;
  its reconstructed Image is byte-identical to the built Image.
- Final test ZIP SHA-256:
  `a5f83b7c88059c8364209091e25e5fa3f70571a2eba2ab70e033bfc34027bbd3`.

These are build/structural checks, not runtime functional or boot tests. No claim
is made about passing any app's integrity checks.

## Điều khiển trong KSU

Sau khi thử boot thành công và xác nhận KSU vẫn có root, cài module SUSFS chính
thức qua KSU > Modules, khởi động lại và mở WebUI của module. Không cần đổi KSU
gốc sang KSU donor. Kernel không tự thêm menu SUSFS vào APK KSU.

Module đã đối chiếu: [susfs4ksu-module R28](https://github.com/sidex15/susfs4ksu-module/releases/tag/v1.5.2%2B_R28).
Nên thử từng tùy chọn, không bật hàng loạt các quy tắc ẩn/chuyển hướng ngay lần
boot đầu. Có thể kiểm tra chỉ-đọc trong terminal đã được KSU cấp root:

```sh
su -c '/data/adb/ksu/bin/ksu_susfs show version'
su -c '/data/adb/ksu/bin/ksu_susfs show variant'
su -c '/data/adb/ksu/bin/ksu_susfs show enabled_features'
```

Kỳ vọng phiên bản `v2.2.0`, variant `NON-GKI`, và danh sách các tính năng trên.
Nếu lỗi boot hoặc mất root, khôi phục boot đã sao lưu qua recovery.

Yêu cầu bổ sung “thuật toán của Tiếp tục kế thừa quyền GitHub” chưa có đặc tả
riêng truy xuất được; bản này không tự suy đoán thêm thuật toán CPU/scheduler.
