#!/usr/bin/env python3
"""Apply eight fixed-size CPU properties to the verified original G965N DTBH."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from validate_dtb import read_fdt_properties, validate


ORIGINAL_SHA256 = '737c4be4f78a5c6a143b2e33a4d25ebbafca1807f8e892349bb412b8025548f4'
CHANGES = {
    ('/schedutil/domain@0', 'up_rate_limit_table'): (5, 1),
    ('/schedutil/domain@0', 'down_rate_limit_table'): (5, 20),
    ('/schedutil/domain@1', 'up_rate_limit_table'): (5, 1),
    ('/schedutil/domain@1', 'down_rate_limit_table'): (5, 20),
    ('/cpufreq/domain@1', 'policy-max'): (1924000, 2704000),
    ('/thermal-zones/BIG/trips/big-switch-on', 'temperature'): (55000, 65000),
    ('/thermal-zones/LITTLE/trips/little-alert1', 'temperature'): (76000, 65000),
    ('/thermal-zones/LITTLE/trips/little-alert1', 'hysteresis'): (5000, 2000),
}


def tune(original):
    assert hashlib.sha256(original).hexdigest() == ORIGINAL_SHA256, 'Wrong original G965N DTBH'
    offset = struct.unpack_from('<I', original, 0x20)[0]
    _, properties = read_fdt_properties(original[offset:], include_offsets=True)
    result = bytearray(original)
    found = set()
    allowed_bytes = set()
    for path, name, payload, position in properties:
        key = (path, name)
        if key not in CHANGES:
            continue
        assert key not in found, f'Duplicate property: {key}'
        old, new = CHANGES[key]
        assert payload == struct.pack('>I', old), f'Unexpected value: {key}'
        start = offset + position
        result[start:start + 4] = struct.pack('>I', new)
        allowed_bytes.update(range(start, start + 4))
        found.add(key)
    assert found == set(CHANGES), f'Missing properties: {set(CHANGES) - found}'
    assert len(result) == len(original)
    assert all(i in allowed_bytes or a == b for i, (a, b) in enumerate(zip(original, result)))
    _, old_props = read_fdt_properties(original[offset:])
    _, new_props = read_fdt_properties(result[offset:])
    assert len(old_props) == len(new_props)
    changed = set()
    for (path, name, before), (new_path, new_name, after) in zip(old_props, new_props):
        assert (path, name) == (new_path, new_name)
        if before != after:
            changed.add((path, name))
    assert changed == set(CHANGES)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_dtb', type=Path)
    parser.add_argument('output_dtb', type=Path)
    args = parser.parse_args()
    validate(args.original_dtb, 'G965N')
    result = tune(args.original_dtb.read_bytes())
    with args.output_dtb.open('xb') as output:
        output.write(result)
    validate(args.output_dtb, 'G965N')
    print(json.dumps({
        'sha256': hashlib.sha256(result).hexdigest(),
        'bytes': len(result),
        'changed_properties': [{'path': p, 'property': n, 'old': a, 'new': b}
                               for (p, n), (a, b) in CHANGES.items()],
        'all_other_bytes_unchanged': True,
    }, indent=2))


if __name__ == '__main__':
    main()
