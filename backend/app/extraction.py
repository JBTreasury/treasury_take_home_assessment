"""Vision extraction -- the one external network dependency (see ADR.md §7, §8, §11).

The caller supplies the httpx.AsyncClient so the connection pool is already warm.
"""

from __future__ import annotations

import base64
import json
import os

import httpx

from .schemas import ExtractedLabelData

MODEL = "claude-sonnet-4-6"
API_URL = "https://api.anthropic.com/v1/messages"

EXTRACTION_PROMPT = """You are reading an alcohol beverage label photograph for a TTB compliance check.

Extract exactly these fields and respond with ONLY a JSON object, no other text:

{
  "brand_name": "the brand name as printed on the label",
  "class_type": "the class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey'",
  "abv": <alcohol by volume as a number, e.g. 45.0>,
  "net_contents": "the net contents as printed, e.g. '750 mL'",
  "name_address": "the bottler/producer name and address, e.g. 'Bottled By Old Tom Distillery, Louisville, KY'",
  "warning_text": "the full government warning statement text, exactly as printed, preserving original casing and punctuation",
  "warning_all_caps_bold": <true if the words 'GOVERNMENT WARNING' visually appear in bold type, false otherwise>,
  "country_of_origin": "country of origin statement if present, e.g. 'Product of Scotland' -- empty string if not on the label"
}

If a field is not visible or not present on the label, use an empty string (or 0 for abv, false for the boolean).
Do not paraphrase or correct the warning_text -- transcribe it exactly as printed, including any errors."""


class ExtractionError(Exception):
    pass


async def extract_label_fields(
    image_bytes: bytes, media_type: str, client: httpx.AsyncClient
) -> ExtractedLabelData:
    """Call the vision LLM once and parse structured fields from the response.

    Raises ExtractionError on any failure -- callers (the batch orchestrator)
    catch this per-item so one bad image doesn't fail an entire batch.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ExtractionError("ANTHROPIC_API_KEY is not configured")

    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        },
                    },
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = await client.post(API_URL, json=payload, headers=headers, timeout=15.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise ExtractionError(f"vision API call failed: {e}") from e

    data = resp.json()
    try:
        text = next(block["text"] for block in data["content"] if block["type"] == "text")
    except (KeyError, StopIteration) as e:
        raise ExtractionError("no text content in vision API response") from e

    # Model may wrap JSON in markdown fences despite instructions -- strip defensively.
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return ExtractedLabelData(**json.loads(cleaned))
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise ExtractionError(f"could not parse extraction result: {e}") from e
