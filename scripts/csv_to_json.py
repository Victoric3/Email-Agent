#!/usr/bin/env python3
"""Simple CSV -> JSON converter for the workspace

Usage:
  python scripts\csv_to_json.py "data/First Arena Moderators - Sheet3.csv"

The script writes a pretty-printed JSON file next to the CSV with the same basename
and converts obvious numeric-looking fields into numbers (removes commas, handles
K/M suffixes, floats).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


def parse_number(s: str):
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None

    # remove surrounding quotes
    s = s.strip('"')

    # handle unit suffixes like 1.2K, 3.4M
    m = re.match(r'^([0-9,.]+)\s*([KMBkmb])?$', s)
    if m:
        num, suffix = m.groups()
        # remove commas
        num = num.replace(",", "")
        try:
            if '.' in num:
                value = float(num)
            else:
                value = int(num)
        except ValueError:
            return s
        if suffix:
            suffix = suffix.upper()
            mul = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}.get(suffix, 1)
            value = value * mul
        return value

    # plain numeric with commas (e.g. "18,325,247.00")
    if re.match(r'^[0-9,]+(\.[0-9]+)?$', s):
        try:
            if '.' in s:
                return float(s.replace(',', ''))
            else:
                return int(s.replace(',', ''))
        except ValueError:
            return s

    # if it looks like a percent
    if s.endswith('%'):
        try:
            return float(s[:-1])
        except ValueError:
            return s

    # fallback: original string
    return s


def convert_csv_to_json(csv_path: Path, json_path: Path):
    with csv_path.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        # strip header names
        reader.fieldnames = [h.strip() if h else h for h in (reader.fieldnames or [])]
        rows = []
        for i, r in enumerate(reader, start=1):
            # derive username first so we can insert serial and username at the top
            name_for_slug = (r.get('Name') or r.get('Handle') or '')
            username = (name_for_slug.strip().split()[0] if name_for_slug else 'unknown')
            username = re.sub(r'[^A-Za-z0-9_]+', '', username).lower() or 'unknown'

            # create dict with serial & username first so they appear at the top when dumped
            obj = {'serial': i, 'username': username}

            for k, v in r.items():
                # preserve original string but try to interpret numbers
                if v is None:
                    obj[k] = None
                    continue
                raw = v.strip()
                parsed = parse_number(raw)
                # prefer parsed numbers when it makes sense
                obj[k] = parsed if parsed is not None and not isinstance(parsed, str) else raw
            # add a stable 1-based serial and a username (first token of Name/Handle)
            obj['serial'] = i
            # derive a username similar to generate_lead_files.slugify
            name_for_slug = obj.get('Name') or obj.get('Handle') or ''
            username = (name_for_slug.strip().split()[0] if name_for_slug else 'unknown')
            username = re.sub(r'[^A-Za-z0-9_]+', '', username).lower() or 'unknown'
            obj['username'] = username
            rows.append(obj)

    with json_path.open('w', encoding='utf-8') as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)


def main(argv: list[str]):
    if len(argv) < 2:
        print("Usage: csv_to_json.py <input.csv> [output.json]")
        raise SystemExit(2)

    csv_file = Path(argv[1])
    if not csv_file.exists():
        print(f"Input file not found: {csv_file}")
        raise SystemExit(2)

    if len(argv) >= 3:
        json_file = Path(argv[2])
    else:
        json_file = csv_file.with_suffix('.json')

    convert_csv_to_json(csv_file, json_file)
    print(f'Wrote JSON -> {json_file}')


if __name__ == '__main__':
    main(sys.argv)
