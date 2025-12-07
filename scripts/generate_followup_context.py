#!/usr/bin/env python3
"""
Tiny script to generate a follow-up context file from placeholders.
Usage:
  python scripts/generate_followup_context.py input.json output_path

input.json example fields used here:
- source_file: (optional) path to original context file for reference
- first_name
- channel_name
- email
- video_url
- reply_text
- company
- phones (list)
- website
- signature

The script writes a readable context file with these details.
"""
import json
import sys
from pathlib import Path

TEMPLATE = """# Follow-up Context for {first_name}

Source context file: {source_file}

First Name: {first_name}
Channel Name: {channel_name}
Email: {email}
Company: {company}
Website: {website}

Video created for them: {video_url}

Email reply (raw):
{reply_text}

Contact Info:
{phones_block}

Signature:
{signature}

Notes:
- This file was generated from a script and contains the follow-up response details. Use it for the next email or marketing flow.
"""


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_followup_context.py <input.json> <output-file-path>")
        sys.exit(2)
    input_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    data = json.loads(input_path.read_text(encoding='utf-8'))

    phones = data.get('phones', [])
    phones_block = "\n".join([f"- {p}" for p in phones]) if phones else "(none)"

    source_file = data.get('source_file','(none)')

    content = TEMPLATE.format(
        source_file=source_file,
        first_name=data.get('first_name',''),
        channel_name=data.get('channel_name',''),
        email=data.get('email',''),
        company=data.get('company',''),
        website=data.get('website',''),
        video_url=data.get('video_url',''),
        reply_text=data.get('reply_text',''),
        phones_block=phones_block,
        signature=data.get('signature','')
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding='utf-8')
    print(f"Wrote followup context to: {out_path}")


if __name__ == '__main__':
    main()
