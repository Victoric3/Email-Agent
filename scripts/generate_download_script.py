import csv
import os
import re

csv_path = r"c:\Users\pharm victor\Desktop\company files\Emails\data\First Arena Moderators - Sheet2.csv"
output_script = r"c:\Users\pharm victor\Desktop\company files\Emails\scripts\download_all_transcripts.ps1"

# Ensure directory exists
os.makedirs(os.path.dirname(output_script), exist_ok=True)

with open(csv_path, 'r', encoding='utf-8') as f:
    # Handle potential BOM or metadata lines if any, but DictReader usually handles headers
    # The file content showed some empty lines at the end, DictReader should handle them or we filter
    reader = csv.DictReader(f)
    rows = list(reader)

commands = []
commands.append('New-Item -ItemType Directory -Force -Path "Context/2025-11-21" | Out-Null')
commands.append('Push-Location "Context/2025-11-21"')

count = 0
for row in rows:
    url = row.get('Video for sales')
    if url and url.strip():
        url = url.strip()
        # User requested command format:
        # yt-dlp --write-auto-subs --sub-lang en --skip-download "URL"
        # We will add --no-warnings to reduce noise if needed, but sticking to request is safer.
        # We will add -o "%(id)s.%(ext)s" to make file identification easier and safer? 
        # The user provided a specific command. I will stick to it. 
        # But I will add --ignore-errors so one failure doesn't stop the script? 
        # PowerShell ; separation means they run sequentially. If one fails, the next runs? 
        # In a .ps1 script, commands run sequentially.
        # I'll just output the command.
        cmd = f'yt-dlp --write-auto-subs --sub-lang en --skip-download "{url}"'
        commands.append(cmd)
        count += 1

commands.append('Pop-Location')

with open(output_script, 'w', encoding='utf-8') as f:
    f.write("\n".join(commands))

print(f"Generated script with {count} download commands.")
