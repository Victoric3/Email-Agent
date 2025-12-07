#!/usr/bin/env python3
"""
Scan repository for potential secrets in files. Useful to run before committing.
Excludes .venv, .git, and common binary/data directories.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Directories to skip
SKIP_DIRS = {'.venv', 'venv', '.git', '__pycache__', 'node_modules', '.mypy_cache'}

PATTERNS = [
    r"mongodb\+srv://",
    r"BEGIN RSA PRIVATE KEY",
    r"BEGIN PRIVATE KEY",
    r"api_key\b",
    r"apikey\b",
    r"access_key\b",
    r"secret_key\b",
    r"aws_secret",
    r"password\s*[:=]",
    r"token\s*[:=]",
    r"Authorization:\s*Bearer",
    r"smtp_password",
]

compiled = re.compile("|".join(PATTERNS), re.IGNORECASE)


def should_skip(path: Path) -> bool:
    """Check if path should be skipped."""
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


for f in ROOT.rglob("**/*"):
    if should_skip(f):
        continue
    if f.is_file():
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        matches = compiled.findall(text)
        if matches:
            print(f"Potential secrets in {f.relative_to(ROOT)}:")
            for m in set(matches):
                print(f"  - {m}")
            print()

print("Scan complete.")
