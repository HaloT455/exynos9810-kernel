#!/usr/bin/env python3
"""Grow a Samsung DTBH entry to its proven per-device minimum size."""

import argparse
import struct
import sys
from pathlib import Path


REGION_SIZES = {
    "G960F": 0x4B000,
    "G965F": 0x4B000,
    "G960N": 0x4B800,
    "G965N": 0x4B800,
    "N960F": 0x4C000,
    "N960N": 0x4C800,
}


def normalize(path, variant):
    source = Path(path)
    data = bytearray(source.read_bytes())
    if len(data) < 0x30 or data[:4] != b"DTBH":
        raise ValueError("missing DTBH header")

    offset, current_size, info, reserved = struct.unpack_from("<IIII", data, 0x20)
    expected_size = REGION_SIZES[variant]
    if offset != 0x800 or info != 0x20 or reserved != 0:
        raise ValueError("unexpected DTBH entry layout")
    if len(data) != offset + current_size:
        raise ValueError("DTBH file size does not match its entry size")
    if current_size > expected_size:
        raise ValueError("%s DTBH entry 0x%x exceeds expected 0x%x" %
                         (variant, current_size, expected_size))

    growth = expected_size - current_size
    if growth:
        data.extend(b"\0" * growth)
        struct.pack_into("<I", data, 0x24, expected_size)
        source.write_bytes(data)

    print("OK %s: DTBH region 0x%x -> 0x%x (growth=0x%x)" %
          (variant, current_size, expected_size, growth))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dtb", help="Samsung DTBH container to normalize in place")
    parser.add_argument("variant", choices=sorted(REGION_SIZES))
    args = parser.parse_args()
    try:
        normalize(args.dtb, args.variant)
    except (OSError, ValueError, struct.error) as exc:
        print("normalize_dtb.py: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
