#!/usr/bin/env python3
"""Lightweight Bedrock client wrapper for the workspace.

This module provides AWSBedrockClient which mirrors the behaviour in the example
you supplied (uses aiohttp and a Bearer token). If AWS_API_KEY is not present the
client will operate in mock mode so the rest of the pipeline can be tested locally.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Optional
import aiohttp
from urllib.parse import quote
from dotenv import load_dotenv

# Load .env automatically so the client picks up AWS_API_KEY and model ids
load_dotenv()

logger = logging.getLogger(__name__)


class AWSBedrockClient:
    def __init__(self):
        self.enabled = False
        self.region = os.getenv("AWS_REGION")
        self.api_key = os.getenv("AWS_API_KEY")
        self.account_id = os.getenv("AWS_ACCOUNT_ID")
        self.primary_model_id = os.getenv(
            "AWS_BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"
        )
        # fallback model (default changed to Sonnet 4.5 per request)
        self.fallback_model_id = os.getenv(
            "AWS_BEDROCK_OPUS_MODEL_ID", "anthropic.claude-sonnet-4-5-20250929-v1:0"
        )

        if self.api_key:
            self.enabled = True
            logger.info("AWS Bedrock client enabled (API key found)")
        else:
            self.enabled = False
            logger.info("AWS Bedrock client running in MOCK mode (no API key)")

    def is_enabled(self) -> bool:
        return self.enabled

    async def converse(self, prompt: str, system: str | None = None, model_id: Optional[str] = None, timeout: int = 120) -> dict:
        """
        Send a 'converse' style request to Bedrock. Returns a dict with the model's text under 'text'.

        If running in mock mode, returns a canned response helpful for testing.
        """
        chosen_model = model_id or self.fallback_model_id

        if not self.enabled:
            # Mock response for offline testing
            debug_text = (
                "[MOCK Bedrock response] This is a simulated Opus 4.1 reply.\n"
                "The service would return an Outreach Dossier + Email following the system prompt and the user prompt."
            )
            return {"text": debug_text, "model": "mock-opus-4.1"}

        model_arn = f"arn:aws:bedrock:{self.region}:{self.account_id}:inference-profile/global.{chosen_model}"
        encoded = quote(model_arn, safe='')
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{encoded}/converse"

        headers = {
            "Content-Type": "application/json",
            "X-Amz-Target": "AWSBedrockRuntime.Converse",
            "Authorization": f"Bearer {self.api_key}",
        }

        # build the payload like the example (messages + optional system)
        messages = []
        # Bedrock 'converse' expects roles to be 'user' or 'assistant' only. Put system
        # instructions into the top-level "system" field (list of text objects) instead.
        if system:
            system_block = [{"text": system}]
        else:
            system_block = None

        # Always send the user message in messages.
        messages.append({"role": "user", "content": [{"text": prompt}]})

        payload = {
            "modelId": model_arn,
            "messages": messages,
            "inferenceConfig": {"temperature": 0.2, "maxTokens": 16384},
            "additionalModelRequestFields": {},
        }

        # attach system block as separate top-level field (Bedrock validation requires this)
        if system_block is not None:
            payload["system"] = system_block

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                text = await resp.text()
                try:
                    result = json.loads(text)
                except Exception:
                    raise RuntimeError(f"Bedrock returned non-JSON (status {resp.status}): {text[:1000]}")

                # return the first candidate text (multiple Bedrock response shapes exist)
                # Try the common 'output' -> 'message' -> 'content' chain first
                if result.get("output") and result["output"].get("message"):
                    content = result["output"]["message"].get("content", [])
                    if content and isinstance(content, list):
                        # content entries may be dicts with 'text' or plain strings
                        first = content[0]
                        if isinstance(first, dict) and 'text' in first:
                            return {"text": first.get("text", ""), "model": chosen_model}
                        if isinstance(first, str):
                            return {"text": first, "model": chosen_model}

                # Some responses use results -> outputs -> content -> items
                if result.get('results') and isinstance(result['results'], list):
                    for r in result['results']:
                        outputs = r.get('outputs') or []
                        for out in outputs:
                            content = out.get('content') or []
                            for item in content:
                                if isinstance(item, dict) and item.get('type') in ('output_text', 'text'):
                                    text = item.get('text') or item.get('value') or ''
                                    if text:
                                        return {"text": text, "model": chosen_model}

                # Last fallback: if top-level returned string
                if isinstance(result, str):
                    return {"text": result, "model": chosen_model}

                raise RuntimeError("Unexpected Bedrock response format: " + json.dumps(result)[:1000])
