#!/usr/bin/env python3
"""Create empty lead files for each record in the JSON produced from the CSV.

Files are created under: Context/2025-11-21/context/
Name format: NN_username.txt (1-based position padded to two digits).
If a file already exists, the script will skip it and report the name.
Username is derived from the record's "Name" (first token lowercased, alphanumeric and underscores).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import sys


def slugify(name: str) -> str:
    name = name.strip().split()[0] if name else 'unknown'
    # keep alphanumeric and underscore
    slug = re.sub(r'[^A-Za-z0-9_]+', '', name)
    return slug.lower() or 'unknown'


def main(json_path: Path, out_dir: Path):
    if not json_path.exists():
        print(f'JSON file not found: {json_path}')
        raise SystemExit(2)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(json_path.read_text(encoding='utf-8'))

    created = []
    skipped = []
    for idx, record in enumerate(data, start=1):
        # prefer explicit serial/username if present in the json
        serial = record.get('serial') or idx
        username = record.get('username') or slugify(record.get('Name') or record.get('Handle') or 'unknown')
        filename = f"{int(serial):02d}_{username}.txt"
        target = out_dir / filename
        if target.exists():
            skipped.append(str(target))
            continue

        # create empty file
        target.write_text('', encoding='utf-8')
        created.append(str(target))

    print(f'Created {len(created)} files, skipped {len(skipped)} already-existing files')
    if created:
        for p in created[:10]:
            print(' +', p)
    if skipped:
        print('\nSkipped (already existed):')
        for p in skipped[:10]:
            print(' -', p)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: generate_lead_files.py <json-file> <out-dir>')
        raise SystemExit(2)

    main(Path(sys.argv[1]), Path(sys.argv[2]))
