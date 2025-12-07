#!/usr/bin/env python3
"""Generate per-lead prompt files from a template and the leads JSON + subtitles.

Usage:
  python scripts\generate_prompts.py \
      --template Context\prompt_pattern.md \
      --json data\"First Arena Moderators - Sheet3.json\" \
      --subs Context\2025-11-21\subs \
      --out Context\temp_prompt

Notes:
 - Skips leads whose serials are in the SKIP_SERIALS set (11 and 24 by request).
 - Matches subtitle files by leading 2-digit serial (e.g. '01_' or '01') in the subs folder.
 - Replaces placeholders in the template:
     [add the lead's name and user name] -> "Name (username)"
     [insert transcript file here(the subtitle file)] -> inline subtitle contents or a note if missing
     [insert json about the lead] -> pretty JSON of that lead's data

"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional

SKIP_SERIALS = {11, 24}


def slugify(name: str) -> str:
    if not name:
        return 'unknown'
    token = name.strip().split()[0]
    slug = re.sub(r'[^A-Za-z0-9_]+', '', token).lower()
    return slug or 'unknown'


def find_subtitle_for(serial: int, subs_dir: Path) -> Optional[Path]:
    # look for files starting with zero-padded index or index+_
    prefix = f"{serial:02d}"
    for f in subs_dir.iterdir():
        if not f.is_file():
            continue
        name = f.name
        if name.startswith(prefix + '_') or name.startswith(prefix):
            return f
    return None


def load_template(template_path: Path) -> str:
    return template_path.read_text(encoding='utf-8')


def generate_prompt(template: str, lead: dict, subtitle_text: Optional[str], subtitle_filename: Optional[str]) -> str:
    out = template

    # name + username
    name = lead.get('Name', 'Unknown')
    username = lead.get('username') or slugify(name)
    # replace the exact placeholder with Name (username)
    out = out.replace("[add the lead's name and user name]", f"{name} ({username})")

    # insert transcript
    if subtitle_text is not None:
        transcript_block = f"---\nTranscript file: {subtitle_filename}\n---\n\n{subtitle_text}\n"
    else:
        transcript_block = f"Transcript file not found for serial {lead.get('serial')}\n"

    out = out.replace('[insert transcript file here(the subtitle file)]', transcript_block)

    # insert lead json
    lead_json = json.dumps(lead, indent=2, ensure_ascii=False)
    out = out.replace('[insert json about the lead]', lead_json)

    # ensure the top includes a short header
    header = f"Lead: {name} ({username}) — serial {lead.get('serial')}\n\n"
    # append the user's requested instruction to the end of each generated prompt
    final_line = "give me the context snippet in a way i can copy and use it"
    # only append if the template doesn't already end with this line (to avoid duplicates)
    if out.strip().endswith(final_line):
        return header + out + "\n"
    return header + out + "\n\n" + final_line + "\n"


def main(args):
    template_path = Path(args.template)
    json_path = Path(args.json)
    subs_dir = Path(args.subs)
    out_dir = Path(args.out)

    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")
    if not json_path.exists():
        raise SystemExit(f"JSON not found: {json_path}")
    if not subs_dir.exists():
        raise SystemExit(f"Subs dir not found: {subs_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    template = load_template(template_path)
    data = json.loads(json_path.read_text(encoding='utf-8'))

    created = []

    for lead in data:
        serial = int(lead.get('serial', -1))
        if serial in SKIP_SERIALS:
            print(f"Skipping serial {serial} as requested")
            continue

        username = lead.get('username') or slugify(lead.get('Name') or lead.get('Handle') or '')
        filename = f"{serial:02d}_{username}.md"
        target = out_dir / filename

        subfile = find_subtitle_for(serial, subs_dir)
        subtitle_text = None
        subtitle_filename = None
        if subfile:
            subtitle_filename = subfile.name
            # read the subtitle; prefer smaller sample to avoid massive files — but we'll include whole file
            subtitle_text = subfile.read_text(encoding='utf-8')

        prompt_text = generate_prompt(template, lead, subtitle_text, subtitle_filename)
        target.write_text(prompt_text, encoding='utf-8')
        created.append(str(target))

    print(f"Created {len(created)} prompt files in {out_dir}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--template', required=True)
    parser.add_argument('--json', required=True)
    parser.add_argument('--subs', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    main(args)
