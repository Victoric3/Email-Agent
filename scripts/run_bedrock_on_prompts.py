#!/usr/bin/env python3
"""Run AWS Bedrock (Opus 4.1) on prompt files and write results into context files.

This script reads all prompt files in a directory (default: Context/temp_prompt),
uses the file contents as the user prompt, calls Bedrock (Opus 4.1) with the provided
system prompt, and writes the returned text to the corresponding file in the
Context/2025-11-21/context folder using the same NN_username.txt naming.

If AWS credentials are not available the script runs in mock mode (writes a simulated response)
so you can test the pipeline offline.

Usage:
  python scripts\run_bedrock_on_prompts.py --prompts Context\temp_prompt --out Context\2025-11-21\context \
        --system-file Context\system_prompt.txt --force

"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re
import logging
from typing import List

from aws_bedrock_client import AWSBedrockClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


DEFAULT_SYSTEM_PROMPT = """
You are the Elite Creative Outreach Strategist for EulaIQ, a company building personalized AI instructors and an animation generation layer. Your job is to analyze raw lead data and produce an Outreach Dossier and a conversion-optimized cold email using the rules provided by the user.
"""


async def process_file(client: AWSBedrockClient, filepath: Path, out_dir: Path, system_prompt: str, force: bool = False, max_retries: int = 3, timeout: int = 120, sem: asyncio.Semaphore | None = None):
    name = filepath.name
    # parse leading serial (NN_...)
    try:
        serial = int(name.split('_', 1)[0])
    except Exception:
        logger.warning(f"Skipping file with non-standard name: {name}")
        return False

    if serial <= 1:
        logger.info(f"Skipping serial {serial} ({name}) per request (start from 02)")
        return False

    out_filename = filepath.with_suffix('.txt').name
    target = out_dir / out_filename

    if target.exists() and not force:
        logger.info(f"Target exists and --force not set, skipping: {target}")
        return False

    prompt_text = filepath.read_text(encoding='utf-8')

    # Heuristic check: if the prompt contains a transcript block with significant
    # textual content, explicitly flag that the transcript contains spoken audio
    # and insert a strong top-level instruction so the model doesn't assume silence.
    transcript_warning = ''
    # look for the 'Transcript file:' marker and following text
    m = re.search(r"Transcript file:\s*.+?\n\n", prompt_text, re.I | re.S)
    if m:
        # extract the block after the marker (up to a following '3. company context' or similar)
        start = m.end()
        tail = prompt_text[start: start + 5000]  # inspect a slice
        # count words — if >30 words, likely has spoken audio
        word_count = len(re.findall(r"\w+", tail))
        if word_count > 30:
            transcript_warning = "\n\n[NOTE FOR MODEL: the following transcript contains SPOKEN AUDIO — do NOT infer the creator is 'silent' unless the transcript is empty or explicitly marked no speech.]\n\n"
            # also add a strong top-level flag at the very beginning of the prompt
            # so the model cannot miss the instruction
            top_flag = "[TRANSCRIPT_HAS_SPOKEN_AUDIO: TRUE]\n\n"
            prompt_text = top_flag + prompt_text[:start] + transcript_warning + prompt_text[start:]

    # prefer the primary model (Sonnet 4.5) per request
    model = client.primary_model_id

    attempt = 0
    response_text = None
    last_exc = None

    async def do_call():
        return await client.converse(prompt_text, system=system_prompt, model_id=model, timeout=timeout)

    # use semaphore for concurrency control if provided
    while attempt < max_retries:
        attempt += 1
        try:
            if sem is not None:
                async with sem:
                    result = await do_call()
            else:
                result = await do_call()

            response_text = result.get('text', '')
            break

        except Exception as e:
            last_exc = e
            logger.warning(f"Attempt {attempt}/{max_retries} failed for {name}: {e}")
            # exponential backoff small jitter
            await asyncio.sleep(attempt * 1.5)

    if response_text is None:
        logger.exception(f"Error calling Bedrock for {name}: {last_exc}")
        response_text = f"[ERROR] Bedrock request failed: {last_exc}\n\nOriginal prompt:\n" + prompt_text[:2000]

    # Write to target
    target.write_text(response_text, encoding='utf-8')
    logger.info(f"Wrote response for {name} -> {target}")
    return True


async def main_async(prompts_dir: Path, out_dir: Path, system_prompt: str, files: List[str], force: bool, concurrency: int = 4, retries: int = 3, timeout: int = 120):
    client = AWSBedrockClient()
    out_dir.mkdir(parents=True, exist_ok=True)

    # find files
    if files:
        paths = [prompts_dir / f for f in files]
    else:
        paths = sorted([p for p in prompts_dir.iterdir() if p.is_file() and p.suffix in {'.md', '.txt'}])

    results = []
    # concurrency value passed by CLI in args
    sem = asyncio.Semaphore(concurrency)

    tasks = [process_file(client, p, out_dir, system_prompt, force=force, max_retries=retries, timeout=timeout, sem=sem) for p in paths]
    results_raw = await asyncio.gather(*tasks)
    for p, ok in zip(paths, results_raw):
        results.append((p.name, ok))

    total = sum(1 for _, ok in results if ok)
    logger.info(f"Completed. Wrote {total} responses out of {len(results)} prompts.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompts', required=False, default='Context/temp_prompt')
    parser.add_argument('--out', required=False, default='Context/2025-11-21/context')
    parser.add_argument('--system-file', required=False, help='Path to a system prompt file')
    parser.add_argument('--files', required=False, nargs='*', help='Specific prompt filenames to process (relative to prompts dir)')
    parser.add_argument('--force', action='store_true', help='Overwrite existing target context files')
    parser.add_argument('--concurrency', type=int, default=4, help='Number of parallel requests to run')
    parser.add_argument('--retries', type=int, default=3, help='Retries per file on failure')
    parser.add_argument('--timeout', type=int, default=120, help='HTTP request timeout in seconds')
    args = parser.parse_args()

    prompts_dir = Path(args.prompts)
    out_dir = Path(args.out)

    if args.system_file:
        system_prompt = Path(args.system_file).read_text(encoding='utf-8')
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    asyncio.run(main_async(prompts_dir, out_dir, system_prompt, args.files or [], force=args.force, concurrency=args.concurrency, retries=args.retries, timeout=args.timeout))


if __name__ == '__main__':
    main()
