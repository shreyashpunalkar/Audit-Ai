"""
AI extraction engine using OpenAI-compatible API (NVIDIA NIM / Groq / Gemini).

Sends extracted document content and returns structured JSON with high speed.
"""
from __future__ import annotations
import json
import logging
import re

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Optimized Prompt Templates ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are a HIGH-PRECISION DOCUMENT EXTRACTION ENGINE.
Extract ALL checksheet information from the document into structured JSON with ZERO DATA LOSS.

RULES:
1. Return ONLY valid JSON matching the exact schema below.
2. Never invent data. Use null for missing values. Preserve exact spelling and text.
3. One source row = one JSON row object. Never skip rows or columns.

SCHEMA FORMAT:
{
  "schema": "https://auditai.com/schemas/checksheet.json",
  "schemaVersion": "1.0",
  "exportedAt": null,
  "savedAt": null,
  "appVersion": "1.0",
  "template": {
    "id": "slugified-title",
    "title": "Title of checksheet",
    "standard": null,
    "version": null,
    "description": null,
    "defaults": null,
    "sections": [
      {
        "section_type": "header or table",
        "section_name": "Section Name",
        "headers": ["Header 1", "Header 2"],
        "rows": [["Value 1", "Value 2"]]
      }
    ]
  },
  "validation": {
    "sheets_detected": 1, "sheets_extracted": 1,
    "sections_detected": 1, "sections_extracted": 1,
    "rows_detected": 1, "rows_extracted": 1,
    "columns_detected": 1, "columns_extracted": 1,
    "checklist_items_detected": 1, "checklist_items_extracted": 1
  }
}"""

TEXT_USER_PROMPT = """Analyse the following checksheet document content and convert it entirely into structured JSON.

DOCUMENT CONTENT:
---
{content}
---

Return ONLY the JSON object."""

IMAGE_OCR_PROMPT = """The following text was extracted via OCR from a scanned checksheet image.
Analyse it carefully and convert all visible data into structured JSON.

OCR TEXT:
---
{content}
---

Return ONLY the JSON object."""


# ─── Client Factory ───────────────────────────────────────────────────────────

def _is_valid_key(key: str) -> bool:
    return bool(key) and not key.startswith("your_")


def _get_client() -> AsyncOpenAI:
    if _is_valid_key(settings.groq_api_key):
        return AsyncOpenAI(
            base_url=settings.groq_base_url,
            api_key=settings.groq_api_key,
        )
    elif _is_valid_key(settings.gemini_api_key):
        return AsyncOpenAI(
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key,
        )
    elif _is_valid_key(settings.nvidia_api_key):
        return AsyncOpenAI(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
        )
    else:
        raise ValueError(
            "Neither NVIDIA_API_KEY, GEMINI_API_KEY, nor GROQ_API_KEY is configured. "
            "Please set your API key in backend/.env to run extraction."
        )


# ─── Response Parsing ─────────────────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    """Strip markdown fences if the model wraps the response."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _parse_json_safe(raw: str) -> dict:
    """Parse JSON with fallback: try whole string, then find first {...} block."""
    cleaned = _clean_json_response(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(
            f"Could not parse valid JSON from AI response. "
            f"First 300 chars: {cleaned[:300]}"
        )


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def run_ai_extraction(
    content: str,
    file_path: str = "",
) -> dict:
    """
    Run AI extraction on document content.
    """
    if settings.mock_ai:
        logger.info("MOCK_AI is enabled. Returning mock checksheet JSON response.")
        import asyncio
        await asyncio.sleep(0.5)  # Fast mock response
        return {
            "schema": "https://auditai.com/schemas/checksheet.json",
            "schemaVersion": "1.0",
            "exportedAt": "2026-07-17T16:00:00Z",
            "savedAt": "2026-07-17T16:00:00Z",
            "appVersion": "1.0",
            "template": {
                "id": "bec-1500-human-rights-audit-checklist",
                "title": "BEC 1500 Human Rights Audit Checklist",
                "standard": "BEC 1500",
                "version": "1.0",
                "description": "Human rights compliance audit checksheet",
                "defaults": None,
                "sections": [
                    {
                        "section_type": "header",
                        "section_name": "Audit Metadata",
                        "headers": ["Field", "Value"],
                        "rows": [
                            ["Inspector", "Ayush Taware"],
                            ["Date", "2026-07-17"],
                            ["Asset", "BEC 1500 Facility"],
                            ["Location", "Main Plant Site"]
                        ]
                    },
                    {
                        "section_type": "table",
                        "section_name": "Inspection Checks",
                        "headers": ["Sr No", "Parameter", "Specification", "Result", "Remarks"],
                        "rows": [
                            ["1", "Verify general availability of data anonymous or and indirect", "Data privacy compliance standard 4.2", "Passed", "Anonymous options are fully implemented."],
                            ["2", "Check for human rights policy communication", "Policy accessibility standards", "Passed", "Policies are posted in all common languages."],
                            ["3", "Verify labor union rights compliance", "Freedom of association guidelines", "Passed", "Regular union coordination meetings held."]
                        ]
                    }
                ]
            },
            "validation": {
                "sheets_detected": 1,
                "sheets_extracted": 1,
                "sections_detected": 2,
                "sections_extracted": 2,
                "rows_detected": 7,
                "rows_extracted": 7,
                "columns_detected": 5,
                "columns_extracted": 5,
                "checklist_items_detected": 3,
                "checklist_items_extracted": 3
            }
        }

    client = _get_client()

    # Fast content truncation (16,000 chars is plenty for checksheets and speeds up prefill)
    trimmed_content = content[:16000].strip()

    user_prompt = TEXT_USER_PROMPT.format(content=trimmed_content)

    if _is_valid_key(settings.groq_api_key):
        model_name = settings.groq_model
    elif _is_valid_key(settings.gemini_api_key):
        model_name = settings.gemini_model
    else:
        model_name = settings.nvidia_model

    logger.info(
        f"Sending to AI ({model_name}) — "
        f"{len(trimmed_content)} chars"
    )

    # Prepare completion kwargs for greedy fast decoding
    completion_kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,  # Greedy decoding (fastest generation & deterministic)
        "max_tokens": 4096,
        "timeout": 45.0,
    }

    # Try response_format={"type": "json_object"} if supported
    try:
        response = await client.chat.completions.create(
            **completion_kwargs,
            response_format={"type": "json_object"}
        )
    except Exception as e:
        logger.debug(f"JSON response_format not supported by provider, retrying without: {e}")
        response = await client.chat.completions.create(**completion_kwargs)

    raw_text = response.choices[0].message.content or ""
    logger.debug(f"AI raw response (first 300 chars): {raw_text[:300]}")

    result = _parse_json_safe(raw_text)
    logger.info(f"AI extraction successful — {len(result)} top-level keys")
    return result
