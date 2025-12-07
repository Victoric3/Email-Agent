#!/usr/bin/env python3
"""
Read scripts/subtitles_mapping.csv, fetch video titles from the mapped URLs
and insert a NOTE with the title at the top of each subtitle (.vtt) file.

This script is careful to not duplicate already-inserted titles.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from typing import Optional

try:
    # use standard library for fetching (no external deps required)
    from urllib.request import urlopen, Request
except Exception:
    print("Failed to import urllib, aborting")
    raise


def fetch_title(url: str) -> Optional[str]:
    """Fetch a page and try to extract a sensible title.

    Prefers og:title then <title> tag. Returns None on failure.
    """
    # First try YouTube's oEmbed endpoint which returns a small JSON with the canonical title
    try:
        oembed = f"https://www.youtube.com/oembed?format=json&url={url}"
        req = Request(oembed, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urlopen(req, timeout=20) as resp:
            raw = resp.read(65536)
            try:
                import json

                data = json.loads(raw.decode(errors="ignore"))
                if isinstance(data, dict) and data.get("title"):
                    return data["title"].strip()
            except Exception:
                # fall through to page parsing
                pass
    except Exception:
        # oEmbed may fail for some URLs — fall back to fetching raw page
        pass

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urlopen(req, timeout=20) as resp:
            raw = resp.read(65536)
            text = raw.decode(errors="ignore")
    except Exception as e:
        print(f"Error fetching {url!r}: {e}")
        return None

    # try og:title — use a simpler extraction approach to avoid complex quoting
    idx = text.lower().find("og:title")
    if idx != -1:
        start = max(0, idx - 300)
        snippet = text[start: idx + 300]
        # try double-quoted content first
        m = re.search(r'content\s*=\s"([^\"]+)"', snippet, re.I)
        if m:
            return m.group(1).strip()
        # try single-quoted content
        m = re.search(r"content\s*=\s'([^']+)'", snippet, re.I)
        if m:
            return m.group(1).strip()

    # fallback to <title>
    m = re.search(r'<title>(.*?)</title>', text, re.I | re.S)
    if m:
        return m.group(1).strip()

    return None


def insert_title_into_vtt(vtt_path: str, title: str) -> bool:
    """Insert NOTE Video title into .vtt file just after the WEBVTT header.

    Returns True if file changed, False otherwise.
    """
    if not os.path.exists(vtt_path):
        print(f"subtitle file missing: {vtt_path}")
        return False

    with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.read()

    if not data.strip():
        print(f"empty file: {vtt_path}")
        return False

    # already present?
    if "NOTE Video title:" in data:
        # if the exact NOTE exists, skip
        print(f"already has title: {vtt_path}")
        return False

    # find WEBVTT header end: after the first blank line following the header block
    # The header block often starts with 'WEBVTT' plus several header lines then an empty line
    lines = data.splitlines(True)

    # find first blank line after the top (first occurrence of a line that's just newline or whitespace)
    insert_index = None
    # ensure the file starts with WEBVTT; if not, we'll prepend at the absolute top
    if lines and lines[0].strip().upper() == "WEBVTT":
        # look for first blank line after line 0
        for i in range(1, min(20, len(lines))):
            if lines[i].strip() == "":
                insert_index = i + 1
                break
        if insert_index is None:
            # no blank line found within first 20 lines, insert after the header line
            insert_index = 1
    else:
        insert_index = 0

    note_line = f"NOTE Video title: {title}\n\n"

    lines.insert(insert_index, note_line)
    new_data = "".join(lines)

    # write back
    with open(vtt_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(new_data)

    print(f"inserted title into: {vtt_path}")
    return True


def main(csv_path: str):
    if not os.path.exists(csv_path):
        print(f"mapping CSV not found: {csv_path}")
        return 2

    changed = 0

    with open(csv_path, newline="", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = (row.get("url") or "").strip()
            vtt_path = (row.get("subtitle_file") or "").strip()
            if not url or not vtt_path:
                print(f"skipping row (no url or no subtitle file): {row.get('index')}")
                continue

            # normalize path separators (CSV used Windows absolute paths)
            vtt_path = vtt_path.replace("\\", os.sep)

            title = fetch_title(url)
            if not title:
                print(f"no title found for {url} — skipping {vtt_path}")
                continue

            success = insert_title_into_vtt(vtt_path, title)
            if success:
                changed += 1

    print(f"done — inserted titles into {changed} file(s)")
    return 0


if __name__ == "__main__":
    csv_path = os.path.join(os.path.dirname(__file__), "subtitles_mapping.csv")
    sys.exit(main(csv_path))
