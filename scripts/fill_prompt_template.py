#!/usr/bin/env python3
"""
Fill a template prompt by replacing placeholders such as [insert context file], [insert email], [insert username]
with the provided source context file contents and email reply text.

Usage:
  python scripts/fill_prompt_template.py input.json template.md output.txt

input.json should contain:
- template_path (optional)
- source_file: path to the context file to insert
- reply_text: full raw reply text to insert
- first_name or channel_name: for username replacement
- video_url: optional to ensure the template's video link is updated

The script writes the filled prompt to output path.
"""
import json
import sys
from pathlib import Path

if len(sys.argv) < 4:
    print("Usage: fill_prompt_template.py <input.json> <template.md> <output.txt>")
    sys.exit(2)

input_path = Path(sys.argv[1])
template_path = Path(sys.argv[2])
out_path = Path(sys.argv[3])

data = json.loads(input_path.read_text(encoding='utf-8'))

# Read template
template = template_path.read_text(encoding='utf-8')

# Read source context file
source_file_path = Path(data.get('source_file'))
if source_file_path.exists():
    source_content = source_file_path.read_text(encoding='utf-8')
else:
    source_content = ''

# Fields to replace
reply_text = data.get('reply_text','')
first_name = data.get('first_name', data.get('channel_name','(unknown)'))
video_url = data.get('video_url','')
channel_name = data.get('channel_name','')

# Prepare replacements
filled = template
# Replace the placeholder tags exactly as in the template
filled = filled.replace('[insert context file]', source_content)
filled = filled.replace('[insert email]', reply_text)
# Common username tokens
filled = filled.replace('[insert username]', first_name)
filled = filled.replace('[insert context file]', source_content)
# If template has a "Now i have made the Promised Video:" line, replace the trailing URL if present
if video_url:
    # Try to find the line that begins with "Now i have made the Promised Video:" and replace it
    filled = filled.replace('Now i have made the Promised Video: https://youtu.be/DJsfFysZJns', f'Now i have made the Promised Video: {video_url}')

# Write output
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(filled, encoding='utf-8')
print(f"Wrote filled prompt to: {out_path}")
