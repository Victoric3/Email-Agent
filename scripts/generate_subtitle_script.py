import csv
import os
from pathlib import Path

# Configuration - update these paths if you moved files
CSV_PATH = r"c:\Users\pharm victor\Desktop\company files\Emails\data\First Arena Moderators - Sheet3.csv"
OUT_PS = r"c:\Users\pharm victor\Desktop\company files\Emails\scripts\download_all_subtitles.ps1"
OUT_BAT = r"c:\Users\pharm victor\Desktop\company files\Emails\scripts\download_subtitles.bat"

# Destination folder used by the generated scripts
DEST_DIR = r"Context/2025-11-21/subs"


def read_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Normalize header keys for safer lookups
        for row in reader:
            # some CSVs have stray BOM or whitespace on headers; normalize
            normalized = {k.strip(): v for k, v in row.items()} if row else {}
            rows.append(normalized)
    return rows


def find_video_field_name(headers):
    candidates = [h for h in headers if h and h.strip().lower().startswith("video")]
    # prefer exact 'video for sales' if present
    for c in candidates:
        if c.strip().lower() == "video for sales":
            return c
    return candidates[0] if candidates else None


def build_commands(rows):
    # find field name
    if not rows:
        return []

    headers = list(rows[0].keys())
    field = find_video_field_name(headers)
    if not field:
        raise RuntimeError("Could not find a 'Video...' column in the CSV headers: %s" % headers)

    entries = []
    for idx, row in enumerate(rows, start=1):
        raw = row.get(field, "")
        if not raw:
            continue
        url = raw.strip()
        if url:
            entries.append((idx, row.get('Name', '').strip(), url))

    total = len(entries)
    pad = max(2, len(str(total)))

    ps_cmds = []
    bat_cmds = []
    # Ensure destination directory exists command in PS and then push to it
    ps_cmds.append(f'New-Item -ItemType Directory -Force -Path "{DEST_DIR}" | Out-Null')
    ps_cmds.append(f'Push-Location "{DEST_DIR}"')

    bat_cmds.append('@echo off')
    bat_cmds.append(f'if not exist "{DEST_DIR}" mkdir "{DEST_DIR}"')
    bat_cmds.append(f'pushd "{DEST_DIR}"')

    for (idx, name, url) in entries:
        prefix = str(idx).zfill(pad)
        # Output file template uses the serial prefix + video id and preserves yt-dlp extension
        out_template = f"{prefix}_%(id)s.%(ext)s"
        # Using only english auto-subs and skip actual video download
        cmd = f'yt-dlp --ignore-errors --no-warnings --write-auto-subs --sub-lang en --skip-download -o "{out_template}" "{url}"'
        ps_cmds.append(cmd)
        bat_cmds.append(cmd)

    ps_cmds.append('Pop-Location')
    bat_cmds.append('popd')
    bat_cmds.append('echo Done. Subtitles will be saved in the destination folder.')

    return ps_cmds, bat_cmds, len(entries)


def write_script(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines))


def main():
    rows = read_rows(CSV_PATH)
    ps_cmds, bat_cmds, count = build_commands(rows)
    write_script(OUT_PS, ps_cmds)
    write_script(OUT_BAT, bat_cmds)
    print(f"Wrote {OUT_PS} and {OUT_BAT} with {count} subtitle download commands (serial-prefixed files).")


if __name__ == '__main__':
    main()
