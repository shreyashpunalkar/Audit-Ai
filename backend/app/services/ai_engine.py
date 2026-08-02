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

SYSTEM_PROMPT = """You are an ultra-precise Document Intelligence AI parser. Your sole objective is to extract data verbatim from the provided document into the requested JSON schema without substituting dummy outputs, generic placeholders, or missing schema values.

CRITICAL PARSING & EXTRACTION RULES:

1. ABSOLUTE ZERO DUMMY/FALLBACK OUTPUTS:
   - NEVER use generic placeholders like "Checksheet Document", "Table 1", "Table 2", or "Section A".
   - Always extract the exact headings present in the document for section names (e.g., "Section 1: Fire Safety").
   - If a top-level field exists in the document text, you MUST populate it. Do not set "standard", "version", or "description" to null if matching text is visible in the header or preamble.

2. VERBATIM FIELD EXTRACTION:
   - Extract the exact main document title as "title" (e.g., "Control Audit Checksheet - Test Template").
   - Extract exact metadata codes (e.g., "OSHA-1.0") into "standard" and versions (e.g., "2026.1") into "version".
   - Extract descriptive paragraphs verbatim for "description".

3. STRICT LITERAL TEXT PRESERVATION:
   - Preserve raw text inside table cells exactly as it appears in the visual or textual layout.
   - Do NOT sanitize, auto-correct, or clean up typos, unclosed brackets, or spacing issues in cell values (e.g., if a cell contains "[  Yes [] No", return "[  Yes [] No", NOT a cleaned "[ ] Yes [ ] No").
   - Retain exact Item IDs, Checklist Questions, Headers, and Comments.

4. REASONING & VALIDATION STEP:
   - Before outputting the JSON, verify every key in the target schema against the raw document text.
   - If any value is set to null or a generic string, perform a second scan of the document header and headings to ensure the data was not simply overlooked.
   - Return ONLY valid JSON matching the exact schema below.

SCHEMA FORMAT:
{
  "schema": "https://auditai.com/schemas/checksheet.json",
  "schemaVersion": "1.0",
  "exportedAt": null,
  "savedAt": null,
  "appVersion": "1.0",
  "template": {
    "id": "slugified-title",
    "title": "Exact Main Heading from Document",
    "standard": "Extracted Standard Code or null",
    "version": "Extracted Version Number or null",
    "description": "Extracted Description Paragraph or null",
    "defaults": null,
    "sections": [
      {
        "section_type": "table",
        "section_name": "Exact Section Heading from Source (e.g. Section 1: Fire Safety)",
        "headers": ["Item ID", "Checklist Question", "Status", "Comments"],
        "rows": [["FS-01", "Are all fire extinguishers unblocked?", "[ ] Yes [ ] No", ""]]
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


def _get_providers() -> list[dict]:
    providers = []
    # Priority 1: Groq (Sub-second speed on LPUs)
    if _is_valid_key(settings.groq_api_key):
        providers.append({
            "name": "Groq",
            "model": settings.groq_model,
            "client": AsyncOpenAI(
                base_url=settings.groq_base_url,
                api_key=settings.groq_api_key,
            ),
        })
    # Priority 2: Gemini
    if _is_valid_key(settings.gemini_api_key):
        providers.append({
            "name": "Gemini",
            "model": settings.gemini_model,
            "client": AsyncOpenAI(
                base_url=settings.gemini_base_url,
                api_key=settings.gemini_api_key,
            ),
        })
    # Priority 3: NVIDIA NIM
    if _is_valid_key(settings.nvidia_api_key):
        providers.append({
            "name": "NVIDIA NIM",
            "model": settings.nvidia_model,
            "client": AsyncOpenAI(
                base_url=settings.nvidia_base_url,
                api_key=settings.nvidia_api_key,
            ),
        })
    return providers


# ─── Response Parsing & Rule Fallback ─────────────────────────────────────────

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


def _build_fallback_json(content: str) -> dict:
    """
    Guaranteed fallback parser when AI providers are unreachable or timing out.
    Extracts headers and key-value rows directly from content.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title = lines[0] if lines else "Document Checksheet"
    title = re.sub(r"^[=\-#\s]+|[=\-#\s]+$", "", title)

    rows = []
    for line in lines[1:]:
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                rows.append(parts)
        elif ":" in line:
            parts = [p.strip() for p in line.split(":", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                rows.append(parts)

    if not rows:
        rows = [["Extracted Line", line] for line in lines[1:25]]

    return {
        "schema": "https://auditai.com/schemas/checksheet.json",
        "schemaVersion": "1.0",
        "exportedAt": None,
        "savedAt": None,
        "appVersion": "1.0",
        "template": {
            "id": re.sub(r"[^\w]+", "-", title.lower()).strip("-") or "audit-checksheet",
            "title": title,
            "standard": None,
            "version": "1.0",
            "description": "Deterministic rule-based extraction",
            "defaults": None,
            "sections": [
                {
                    "section_type": "table",
                    "section_name": "Extracted Data",
                    "headers": ["Item / Parameter", "Value / Detail"],
                    "rows": rows[:50]
                }
            ]
        },
        "validation": {
            "sheets_detected": 1, "sheets_extracted": 1,
            "sections_detected": 1, "sections_extracted": 1,
            "rows_detected": len(rows), "rows_extracted": len(rows),
            "columns_detected": 2, "columns_extracted": 2,
            "checklist_items_detected": len(rows), "checklist_items_extracted": len(rows)
        }
    }


# ─── Main Entry Point ─────────────────────────────────────────────────────────

async def run_ai_extraction(
    content: str,
    file_path: str = "",
) -> dict:
    """
    Run AI extraction on document content with automatic multi-provider failover.
    """
    if settings.mock_ai:
        logger.info("MOCK_AI is enabled. Returning mock checksheet JSON response.")
        import asyncio
        await asyncio.sleep(0.5)
        return _build_fallback_json(content)

    providers = _get_providers()
    if not providers:
        logger.warning("No valid AI API key found. Using deterministic fallback parser.")
        return _build_fallback_json(content)

    trimmed_content = content[:16000].strip()
    user_prompt = TEXT_USER_PROMPT.format(content=trimmed_content)

    errors = []

    for prov in providers:
        provider_name = prov["name"]
        model_name = prov["model"]
        client = prov["client"]

        logger.info(f"Attempting AI extraction via {provider_name} ({model_name})...")

        completion_kwargs = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 4096,
            "timeout": 15.0,  # 15s timeout per provider to prevent Vercel 60s function limit
        }

        try:
            try:
                response = await client.chat.completions.create(
                    **completion_kwargs,
                    response_format={"type": "json_object"}
                )
            except Exception as e:
                logger.debug(f"[{provider_name}] json_object response_format retry: {e}")
                response = await client.chat.completions.create(**completion_kwargs)

            raw_text = response.choices[0].message.content or ""
            result = _parse_json_safe(raw_text)
            logger.info(f"AI extraction successful via {provider_name} ({model_name})")
            return result

        except Exception as err:
            logger.warning(f"AI extraction via {provider_name} ({model_name}) failed: {err}")
            errors.append(f"{provider_name}: {err}")
            # Try next configured provider in failover loop!
            continue

    logger.error(f"All AI providers failed ({errors}). Returning fallback extraction JSON.")
    return _build_fallback_json(content)
