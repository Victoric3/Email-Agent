#!/usr/bin/env python3
"""Truncate transcript blocks in prompt files to avoid exceeding model input limits.

This script scans files in a directory (default: Context/temp_prompt) for the
pattern inserted by generate_prompts.py:

---\nTranscript file: <filename>\n---\n\n<full transcript...>

It truncates the transcript text to a configurable number of characters or lines
and writes the modified file in-place while saving an original copy as
<filename>.orig.

Usage:
  python scripts\truncate_transcripts.py --dir Context\temp_prompt --max-chars 3000

Default: max-chars=3000 (approx safe input size). Use --dry-run to preview.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional


TRANSCRIPT_HEADER_RE = re.compile(r"---\s*\n\s*Transcript file:\s*(?P<fname>.+?)\s*\n---\s*\n\s*", re.I | re.S)


def truncate_text(text: str, max_chars: Optional[int], max_lines: Optional[int]) -> str:
    if max_lines is not None:
        lines = text.splitlines()
        if len(lines) > max_lines:
            kept = lines[:max_lines]
            return "\n".join(kept) + f"\n\n[TRANSCRIPT TRUNCATED: kept first {max_lines} lines]"

    if max_chars is not None:
        if len(text) > max_chars:
            kept = text[:max_chars]
            return kept + f"\n\n[TRANSCRIPT TRUNCATED: kept first {max_chars} chars]"

    return text


def process_file(path: Path, max_chars: Optional[int], max_lines: Optional[int], dry_run: bool = False) -> bool:
    txt = path.read_text(encoding='utf-8')
    m = TRANSCRIPT_HEADER_RE.search(txt)
    if not m:
        return False

    header_end = m.end()

    # try to find end of transcript — look for next numbered section '3. company context' or end of file
    tail_match = re.search(r"\n\s*3\.\s*company context", txt[header_end:], re.I)
    if tail_match:
        transcript_end = header_end + tail_match.start()
    else:
        # if not found, attempt to find next '---' divider that starts at column
        next_div = re.search(r"\n---\s*\n", txt[header_end:])
        if next_div:
            transcript_end = header_end + next_div.start()
        else:
            # fallback: until end of file
            transcript_end = len(txt)

    transcript = txt[header_end:transcript_end]

    new_transcript = truncate_text(transcript, max_chars, max_lines)

    if new_transcript == transcript:
        return False

    new_txt = txt[:header_end] + new_transcript + txt[transcript_end:]

    if dry_run:
        print(f"Would truncate: {path} (original {len(transcript)} chars -> {len(new_transcript)} chars)")
        return True

    # backup original
    backup = path.with_suffix(path.suffix + '.orig')
    if not backup.exists():
        path.replace(backup)
        # write modified content to original filename
        path.write_text(new_txt, encoding='utf-8')
    else:
        # if backup already exists, just overwrite file
        path.write_text(new_txt, encoding='utf-8')

    print(f"Truncated: {path} (new size {len(new_transcript)} chars) — backup saved to {backup.name}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', required=False, default='Context/temp_prompt')
    parser.add_argument('--max-chars', type=int, default=3000)
    parser.add_argument('--max-lines', type=int, default=None)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    path = Path(args.dir)
    if not path.exists():
        raise SystemExit(f"Directory not found: {path}")

    files = sorted([p for p in path.iterdir() if p.is_file() and p.suffix in {'.md', '.txt'}])
    changed = 0

    for f in files:
        ok = process_file(f, args.max_chars, args.max_lines, dry_run=args.dry_run)
        if ok:
            changed += 1

    print(f"Processed {len(files)} files — changed {changed} files")


if __name__ == '__main__':
    main()
