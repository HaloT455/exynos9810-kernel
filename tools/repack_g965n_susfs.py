#!/usr/bin/env python3
"""Replace the G965N BSDIFF40 kernel and optional verified Smooth65 DTB payload."""
import argparse
import copy
import hashlib
import json
import zipfile
from pathlib import Path

import bsdiff4

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('original_zip', type=Path)
parser.add_argument('image', type=Path)
parser.add_argument('output_zip', type=Path)
parser.add_argument('--dtb', type=Path, help='DTBH produced by tune_g965n_dtb.py')
args = parser.parse_args()
expected_original = '4ad9f321f1710a7e7177040d37dff54e8664a546dd9c89199df03bc00cc15f14'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(args.original_zip.read_bytes()) == expected_original, 'Wrong original ZIP'
assert args.original_zip.resolve() != args.output_zip.resolve(), 'Do not overwrite local baseline'
assert not args.output_zip.exists(), 'Output already exists'
image = args.image.read_bytes()
assert image[0x38:0x3c] == b'ARM\x64', 'Not an ARM64 raw Image'
assert len(image) > 20_000_000, 'Unexpectedly small Image'
payload = 'floyd/G965N-kernel'
with zipfile.ZipFile(args.original_zip) as original:
    assert original.testzip() is None
    names = original.namelist()
    assert len(names) == len(set(names)), 'Duplicate entries'
    base = original.read('floyd/G960F-kernel')
    assert original.read(payload).startswith(b'BSDIFF40')
    delta = bsdiff4.diff(base, image)
    assert bsdiff4.patch(base, delta) == image
    replacements = {payload: delta}
    if args.dtb:
        from tune_g965n_dtb import tune
        from validate_dtb import validate
        validate(args.dtb, 'G965N')
        dtb_base = original.read('floyd/G960F-dtb')
        original_dtb = bsdiff4.patch(dtb_base, original.read('floyd/G965N-dtb'))
        dtb = args.dtb.read_bytes()
        assert dtb == tune(original_dtb), 'DTB changes exceed the Smooth65 profile'
        dtb_delta = bsdiff4.diff(dtb_base, dtb)
        assert bsdiff4.patch(dtb_base, dtb_delta) == dtb
        replacements['floyd/G965N-dtb'] = dtb_delta
    with zipfile.ZipFile(args.output_zip, 'x') as out:
        out.comment = original.comment
        for entry in original.infolist():
            out.writestr(copy.copy(entry), replacements.get(entry.filename, original.read(entry.filename)))
    with zipfile.ZipFile(args.output_zip) as out:
        assert out.testzip() is None
        assert out.namelist() == names
        changed = [name for name in names if out.read(name) != original.read(name)]
        assert set(changed) == set(replacements), changed
        assert bsdiff4.patch(out.read('floyd/G960F-kernel'), out.read(payload)) == image
        if args.dtb:
            assert bsdiff4.patch(out.read('floyd/G960F-dtb'), out.read('floyd/G965N-dtb')) == dtb
        for old, new in zip(original.infolist(), out.infolist()):
            for attr in ('filename', 'date_time', 'compress_type', 'external_attr', 'extra', 'comment'):
                assert getattr(old, attr) == getattr(new, attr), (old.filename, attr)
print(json.dumps({
    'original_zip_sha256': expected_original,
    'output_zip': str(args.output_zip.resolve()),
    'output_zip_sha256': sha(args.output_zip.read_bytes()),
    'image_sha256': sha(image),
    'image_bytes': len(image),
    'delta_bytes': len(delta),
    'entries_checked': len(names),
    'changed_entries': changed,
    'dtb_sha256': sha(dtb) if args.dtb else None,
    'all_other_models_unchanged': True,
    'g965n_dtb_unchanged': not bool(args.dtb),
    'round_trip': 'PASS',
    'boot_tested': False,
}, indent=2))
