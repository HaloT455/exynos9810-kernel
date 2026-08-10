#!/usr/bin/env python3
"""Validate Exynos9810 DTBH/FDT invariants without rewriting the device tree."""

import argparse
import struct
import sys
from pathlib import Path


DTBH_MAGIC = b"DTBH"
FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9

REGION_SIZES = {
    "G960F": 0x4B000,
    "G965F": 0x4B000,
    "G960N": 0x4B800,
    "G965N": 0x4B800,
    "N960F": 0x4C000,
    "N960N": 0x4C800,
}


def align4(value):
    return (value + 3) & ~3


def u32be(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def cstring(data, offset, limit):
    end = data.find(b"\0", offset, limit)
    if end < 0:
        raise ValueError("unterminated FDT string")
    return data[offset:end].decode("ascii", "replace"), end + 1


def read_fdt_properties(fdt):
    if len(fdt) < 40 or u32be(fdt, 0) != FDT_MAGIC:
        raise ValueError("invalid FDT magic")

    total = u32be(fdt, 4)
    struct_offset = u32be(fdt, 8)
    strings_offset = u32be(fdt, 12)
    strings_size = u32be(fdt, 32)
    struct_size = u32be(fdt, 36)
    if total < 40 or total > len(fdt):
        raise ValueError("FDT totalsize exceeds its DTBH region")
    if struct_offset + struct_size > total:
        raise ValueError("FDT structure block is out of bounds")
    if strings_offset + strings_size > total:
        raise ValueError("FDT strings block is out of bounds")

    pos = struct_offset
    struct_end = struct_offset + struct_size
    strings_end = strings_offset + strings_size
    nodes = []
    properties = []

    while pos + 4 <= struct_end:
        token = u32be(fdt, pos)
        pos += 4
        if token == FDT_BEGIN_NODE:
            name, pos = cstring(fdt, pos, struct_end)
            pos = align4(pos)
            nodes.append(name)
        elif token == FDT_END_NODE:
            if not nodes:
                raise ValueError("malformed FDT node stack")
            nodes.pop()
        elif token == FDT_PROP:
            if pos + 8 > struct_end:
                raise ValueError("truncated FDT property header")
            length = u32be(fdt, pos)
            name_offset = u32be(fdt, pos + 4)
            payload_start = pos + 8
            payload_end = payload_start + length
            if payload_end > struct_end:
                raise ValueError("truncated FDT property payload")
            if name_offset >= strings_size:
                raise ValueError("FDT property name is out of bounds")
            name, _ = cstring(fdt, strings_offset + name_offset, strings_end)
            path = "/" + "/".join(node for node in nodes if node)
            properties.append((path, name, fdt[payload_start:payload_end]))
            pos = align4(payload_end)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError("unknown FDT token 0x%x at 0x%x" % (token, pos - 4))
    else:
        raise ValueError("FDT_END token was not found")

    return total, properties


def one_property(properties, path_suffix, name):
    matches = [payload for path, prop, payload in properties
               if path.endswith(path_suffix) and prop == name]
    if len(matches) != 1:
        raise ValueError("expected one %s/%s property, found %d" %
                         (path_suffix, name, len(matches)))
    return matches[0]


def validate(path, variant):
    data = Path(path).read_bytes()
    expected_region = REGION_SIZES[variant]
    expected_total = 0x800 + expected_region

    if len(data) != expected_total:
        raise ValueError("%s DTBH size is 0x%x, expected 0x%x" %
                         (variant, len(data), expected_total))
    if data[:4] != DTBH_MAGIC:
        raise ValueError("missing DTBH magic")

    version, entries, chip = struct.unpack_from("<III", data, 4)
    offset, region_size, info, reserved = struct.unpack_from("<IIII", data, 0x20)
    if version != 2 or entries != 1 or chip != 9810:
        raise ValueError("unexpected DTBH header version/entry/chip values")
    if offset != 0x800:
        raise ValueError("DTBH FDT offset is 0x%x, expected 0x800" % offset)
    if region_size != expected_region:
        raise ValueError("DTBH region is 0x%x, expected 0x%x" %
                         (region_size, expected_region))
    if info != 0x20 or reserved != 0:
        raise ValueError("DTBH entry info/reserved is 0x%x/0x%x, expected 0x20/0" %
                         (info, reserved))

    fdt = data[offset:offset + region_size]
    total, properties = read_fdt_properties(fdt)
    if any(fdt[total:]):
        raise ValueError("non-zero data follows the FDT inside its DTBH region")

    for partition in ("system", "vendor", "odm"):
        fs_type = one_property(properties, "/fstab/" + partition, "type")
        if fs_type.rstrip(b"\0") != b"erofs":
            raise ValueError("%s fstab type is not erofs" % partition)

    idle_ip = one_property(properties, "/exynos-powermode", "idle-ip")
    entries = [item for item in idle_ip.split(b"\0") if item]
    if not entries or entries[0] != b"10510000.pwm":
        raise ValueError("idle-ip does not start with 10510000.pwm")
    if b"14230000.adc" not in entries:
        raise ValueError("idle-ip lacks the complete 14230000.adc entry")
    if b"\x0c230000.adc" in idle_ip or b"230000.adc" in entries:
        raise ValueError("idle-ip contains the known dtc-corrupted ADC entry")

    if b"ramoops" in fdt[:total].lower():
        raise ValueError("unexpected ramoops node/property is enabled in the FDT")

    print("OK %s: DTBH=0x%x region=0x%x FDT=0x%x info=0x%x "
          "fstab=erofs idle-ip=%d ramoops=0" %
          (variant, len(data), region_size, total, info, len(entries)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dtb", help="Samsung DTBH container")
    parser.add_argument("variant", choices=sorted(REGION_SIZES))
    args = parser.parse_args()
    try:
        validate(args.dtb, args.variant)
    except (OSError, ValueError, struct.error) as exc:
        print("validate_dtb.py: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
