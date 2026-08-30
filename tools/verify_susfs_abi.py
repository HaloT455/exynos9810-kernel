#!/usr/bin/env python3
"""Host-only ABI checks; never issues reboot/prctl or talks to a live kernel."""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('userspace', type=Path, help='susfs4ksu-binaries universal-binary checkout')
args = parser.parse_args()
userspace = args.userspace.resolve()
kernel = (root / 'include/linux/susfs.h').read_text()
user = (userspace / 'include/susfs.h').read_text()
pairs = {
    'sus_path': 'sus_path_v2000_new',
    'hide_sus_mnts_for_non_su_procs': 'hide_sus_mnts_v2000',
    'sus_kstat': 'sus_kstat_v2100',
    'uname': 'uname_v2000',
    'log': 'log_v2000',
    'spoof_cmdline_or_bootconfig': 'spoof_cmdline_v2000',
    'open_redirect': 'open_redirect_v2100',
    'sus_map': 'sus_map_v2000',
    'avc_log_spoofing': 'avc_log_v2000',
    'enabled_features': 'enabled_features_v2000',
    'variant': 'variant_v2000',
    'version': 'version_v2000',
}

def struct(text, name):
    match = re.search(r'\bstruct\s+' + re.escape(name) + r'\s*\{(.*?)\};', text, re.S)
    assert match, name
    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', match[1], flags=re.S)
    fields = re.findall(r'\b(\w+)\s*(?:\[[^]]+\])?\s*;', body)
    return 'struct ' + name + ' {' + body + '};\n', fields

source = '''#include <stdbool.h>
#include <stddef.h>
#define SUSFS_MAX_LEN_PATHNAME 256
#define __NEW_UTS_LEN 64
#define SUSFS_FAKE_CMDLINE_OR_BOOTCONFIG_SIZE 8192
#define SUSFS_ENABLED_FEATURES_SIZE 8192
_Static_assert(sizeof(long) == 8, "This test requires an LP64 host like ARM64");
'''
field_count = 0
for kernel_suffix, user_name in pairs.items():
    kernel_name = 'st_susfs_' + kernel_suffix
    kd, kf = struct(kernel, kernel_name)
    ud, uf = struct(user, user_name)
    assert kf == uf, (kernel_name, kf, uf)
    source += kd + ud
    source += f'_Static_assert(sizeof(struct {kernel_name}) == sizeof(struct {user_name}), "{kernel_name} size");\n'
    for field in kf:
        source += f'_Static_assert(offsetof(struct {kernel_name}, {field}) == offsetof(struct {user_name}, {field}), "{kernel_name}.{field} offset");\n'
        source += f'_Static_assert(sizeof(((struct {kernel_name}*)0)->{field}) == sizeof(((struct {user_name}*)0)->{field}), "{kernel_name}.{field} size");\n'
        field_count += 1
source += 'int main(void) { return 0; }\n'

def constants(text):
    return dict(re.findall(r'^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)\b', text, re.M))

kc = constants((root / 'include/linux/susfs_def.h').read_text())
uc = constants(user)
aliases = {'CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS': 'CMD_SUSFS_HIDE_SUS_MNTS'}
bridge = (root / 'KernelSU-Next/kernel/susfs_bridge.c').read_text()
commands = re.findall(r'case (CMD_SUSFS_\w+):', bridge)
for command in commands + ['SUSFS_MAGIC']:
    assert int(kc[command], 0) == int(uc[aliases.get(command, command)], 0), command
assert '#define KSTAT_SPOOF_CTIME_TV_SEC (1 << 8)' in kernel
supercalls = (root / 'KernelSU-Next/kernel/supercalls.c').read_text()
assert 'if (current_uid().val != 0)' in supercalls
assert 'return ksu_susfs_handle_cmd(cmd, arg);' in supercalls
assert 'susfs_init();' in (root / 'KernelSU-Next/kernel/ksu.c').read_text()
assert 'susfs_start_sdcard_monitor_fn();' in (root / 'KernelSU-Next/kernel/ksud.c').read_text()

with tempfile.TemporaryDirectory(prefix='susfs-abi-') as tmp:
    executable = str(Path(tmp) / 'abi')
    subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', '-x', 'c', '-', '-o', executable], input=source, text=True, check=True)
    subprocess.run([executable], check=True)
    version_test = '#include "susfs.h"\nint main(void) { return parse_version_string("v2.2.0") != 2100; }\n'
    subprocess.run(['cc', '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections', '-I', str(userspace / 'include'), '-x', 'c', '-', str(userspace / 'src/detect/version.c'), '-o', executable], input=version_test, text=True, check=True)
    subprocess.run([executable], check=True)
print(f'PASS: {len(pairs)} ABI structures, {field_count} fields, {len(commands)} commands, root gate, init hooks, v2.2.0 detection.')
