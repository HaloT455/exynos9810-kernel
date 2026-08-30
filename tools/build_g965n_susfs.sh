#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
baseline=${1:?Usage: build_g965n_susfs.sh ORIGINAL_G965N_IMAGE}
test "$(git -C KernelSU-Next rev-parse HEAD)" = 1ce19e536de730829b62d0d23dbd96c6ec809e2f
compiler=${DS_ACK_TOOLCHAIN:-$root/../compiler/clang-20.0.0-r547379}
test -x "$compiler/bin/clang"
export PATH="$compiler/bin:$PATH"
for tool in bc cpio perl python3 tar xz clang ld.lld llvm-ar llvm-nm; do
    command -v "$tool" >/dev/null || { echo "Missing build dependency: $tool" >&2; exit 1; }
done
export ARCH=arm64 SUBARCH=arm64 ANDROID_MAJOR_VERSION=q PLATFORM_VERSION=13.0.0
export CC=clang REAL_CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm
export OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump READELF=llvm-readelf STRIP=llvm-strip
export LLVM=1 KALLSYMS_EXTRA_PASS=1 KSU_MANUAL_HOOK=y CONFIG_KSU_MANUAL_HOOK=y
export DS_ACK_PIN_WIREGUARD=1
export CONFIG_MACH_EXYNOS9810_STAR2LTE_KOR=y
export CONFIG_THINLTO=y CONFIG_UNIFIEDLTO=y CONFIG_LLVM_MLGO_REGISTER=y
export CONFIG_LLVM_POLLY=y CONFIG_LLVM_DFA_JUMP_THREAD=y
export LOCALVERSION=${DS_ACK_LOCALVERSION:--DS-ACK-V1.12-G965N-08.30.2026-KSU-SUSFS220}
if [ -f patches/kernelsu-original-susfs220.patch ]; then
    if git -C KernelSU-Next apply --check ../patches/kernelsu-original-susfs220.patch; then
        git -C KernelSU-Next apply ../patches/kernelsu-original-susfs220.patch
    else
        git -C KernelSU-Next apply --reverse --check ../patches/kernelsu-original-susfs220.patch
    fi
fi
bash scripts/extract-ikconfig "$baseline" > .config
test -s .config
cp .config baseline-g965n.config
make ARCH=arm64 CC=clang olddefconfig
python3 - <<'PY'
from pathlib import Path
before = set(Path('baseline-g965n.config').read_text().splitlines())
after = set(Path('.config').read_text().splitlines())
changes = {line for line in before ^ after if line.startswith(('CONFIG_', '# CONFIG_'))}
unexpected = {line for line in changes if 'CONFIG_KSU_SUSFS' not in line}
assert not unexpected, f'Unexpected configuration changes: {unexpected}'
assert 'CONFIG_KSU_SUSFS=y' in after
assert '# CONFIG_ALWAYS_PERMISSIVE is not set' in after
print('Verified: only SUSFS configuration was added to the uploaded G965N kernel.')
PY
make ARCH=arm64 CC=clang -j"${DS_ACK_JOBS:-6}" Image
llvm-nm -n vmlinux > susfs-symbols.txt
for symbol in ksu_susfs_handle_cmd susfs_init susfs_show_version susfs_add_sus_path ksu_handle_sys_reboot; do
    grep -q " ${symbol}$" susfs-symbols.txt
done
test -s arch/arm64/boot/Image
sha256sum arch/arm64/boot/Image
