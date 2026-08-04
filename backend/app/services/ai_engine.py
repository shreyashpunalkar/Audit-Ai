"""
AI extraction engine using OpenAI-compatible API (NVIDIA NIM / Groq / Gemini).

Sends extracted document content and returns structured JSON with high speed.
"""
from __future__ import annotations
import json
import logging
import re
import uuid as _uuid
from datetime import datetime, timezone

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_SCHEMA = "com.audito.checksheet"
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_STANDARD = "BEC 1500:2024"
DEFAULT_VERSION = "1.0"
DEFAULT_LIKERT_MIN = 0
DEFAULT_LIKERT_MAX = 5
DEFAULT_THRESHOLD = 3

# The BEC 1500 six-point maturity scale (0..5) used as the default for all templates.
DEFAULT_SCALE_POINTS = [
    {"value": 0, "label": "Not Established/ Not Addressed", "guidance": "", "labelOverridden": False},
    {"value": 1, "label": "Only Intent demonstrated(e.g. verbally indirectly)", "guidance": "", "labelOverridden": False},
    {"value": 2, "label": "Policy/ Process evidence  Available, but implementation is not seen. ", "guidance": "", "labelOverridden": False},
    {"value": 3, "label": "Fair Implementation (not complete) seen for the process along with the process/ policy definition in all areas, no communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": False},
    {"value": 4, "label": "Implementation seen for the process along with the process/ policy definition in all areas, with  communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": False},
    {"value": 5, "label": "Maturity seen in Implementation  (More than 12 months or across multiple verticals/ Departments) internally and communicated to Stakeholders and stakeholder participation also seen. ", "guidance": "", "labelOverridden": False},
]

# ─── Helper ───────────────────────────────────────────────────────────────────

def _uuid4() -> str:
    return str(_uuid.uuid4())


def _timestamp_z() -> str:
    """ISO 8601 timestamp with millisecond precision and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _default_scale_points() -> list[dict]:
    """Return a deep copy of the default 0..5 BEC maturity scale."""
    return [dict(sp) for sp in DEFAULT_SCALE_POINTS]


# ─── Optimized Prompt Templates ───────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Document Intelligence Lead and Lead QA Automation Engineer. Your objective is to extract checksheet / audit-checklist document data into a target JSON schema with 100% literal data integrity, full top-level metadata fidelity, and strict vertical row isolation.

--- 1. AUDIT CHECKLIST & EXTRACTION DIRECTIVES ---

1. METADATA FLAW PREVENTION:
   - COMPLETE TITLE MATCH: Extract the FULL title string from Cell A1 / Main Header without trimming words.
   - ID / VERSION MAPPING: Look for Audit IDs, Document Reference numbers, or revision codes in header metadata blocks. If a "Version" label is absent but a "Doc Ref", "Audit ID", or revision code exists, assign that ID string to the "version" property.
   - PIPE-SEPARATED METADATA: Split pipe-separated headers cleanly -> "standard" gets the standard code, "version" gets the version string.

2. LITERAL DATA INTEGRITY:
   - Preserve raw cell text exactly as written, including unicode characters, special symbols, raw formatting, typos, and brackets.
   - Do NOT use dummy placeholders or generic default schema names.

3. SECTION HIERARCHY:
   - Build the section tree from document headings. Top-level headings become top-level sections; sub-headings become children.
   - Each section carries an id, code, title, description, weight, children (nested sections), and questions.

4. SCALE EXTRACTION:
   - If the document defines a rating scale (e.g. 0-5 with label descriptions), extract those labels and guidance text into template.defaults.scalePoints.
   - Each individual question should carry its own likert.scalePoints with the full rating scale including guidance text per level (extracted from the document).
   - If no explicit scale is found, use the default six-point BEC 1500 scale (0-5) shown in the schema below.

5. HEADER METADATA SEPARATION:
   - Extract document-level metadata (Standards, Audit IDs, Revisions) STRICTLY into template.standard and template.version.
   - NEVER create table rows out of header/metadata key-value pairs.
   - Strip document artifacts like "Sheet: " or "Form: " from template.title.

Return ONLY valid JSON matching the exact schema below.

SCHEMA FORMAT:
{
  "schema": "com.audito.checksheet",
  "schemaVersion": "1.0.0",
  "exportedAt": null,
  "savedAt": null,
  "appVersion": "0.1.0",
  "template": {
    "id": "template-<uuid4>",
    "title": "Exact Main Heading from Document",
    "standard": "BEC 1500:2024",
    "version": "1.0",
    "description": "Extracted Description Paragraph or null",
    "defaults": {
      "questionType": "likert_observation",
      "likertMin": 0,
      "likertMax": 5,
      "required": true,
      "evidenceRequired": true,
      "weight": 1,
      "threshold": 3,
      "scalePoints": [
        {"value": 0, "label": "Not Established/ Not Addressed", "guidance": "", "labelOverridden": false},
        {"value": 1, "label": "Only Intent demonstrated(e.g. verbally indirectly)", "guidance": "", "labelOverridden": false},
        {"value": 2, "label": "Policy/ Process evidence  Available, but implementation is not seen. ", "guidance": "", "labelOverridden": false},
        {"value": 3, "label": "Fair Implementation (not complete) seen for the process along with the process/ policy definition in all areas, no communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": false},
        {"value": 4, "label": "Implementation seen for the process along with the process/ policy definition in all areas, with  communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": false},
        {"value": 5, "label": "Maturity seen in Implementation  (More than 12 months or across multiple verticals/ Departments) internally and communicated to Stakeholders and stakeholder participation also seen. ", "guidance": "", "labelOverridden": false}
      ]
    },
    "sections": [
      {
        "id": "section-<uuid4>",
        "code": "",
        "title": "Exact Section Heading from Source",
        "description": "Section description or empty string",
        "weight": 1,
        "children": [
          {
            "id": "section-<uuid4>",
            "code": "",
            "title": "Sub-section Heading",
            "description": "",
            "weight": 1,
            "children": [],
            "questions": [
              {
                "id": "question-<uuid4>",
                "title": "Exact question text from the document",
                "helpText": "Guidance / audit instruction text for this question",
                "type": "likert_observation",
                "required": true,
                "evidenceRequired": true,
                "weight": 1,
                "threshold": 3,
                "likert": {
                  "min": 0,
                  "max": 5,
                  "scalePoints": [
                    {"value": 0, "label": "Not Established/ Not Addressed", "guidance": "", "labelOverridden": false},
                    {"value": 1, "label": "Only Intent demonstrated(e.g. verbally indirectly)", "guidance": "", "labelOverridden": false},
                    {"value": 2, "label": "Policy/ Process evidence  Available, but implementation is not seen. ", "guidance": "", "labelOverridden": false},
                    {"value": 3, "label": "Fair Implementation (not complete) seen for the process along with the process/ policy definition in all areas, no communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": false},
                    {"value": 4, "label": "Implementation seen for the process along with the process/ policy definition in all areas, with  communication to stakeholders such as suppliers. ", "guidance": "", "labelOverridden": false},
                    {"value": 5, "label": "Maturity seen in Implementation  (More than 12 months or across multiple verticals/ Departments) internally and communicated to Stakeholders and stakeholder participation also seen. ", "guidance": "", "labelOverridden": false}
                  ]
                }
              }
            ]
          }
        ],
        "questions": []
      }
    ],
    "sectionNumberingTypes": [
      "numeric",
      "upper_alpha",
      "lower_alpha",
      "lower_roman",
      "upper_roman"
    ]
  }
}

IMPORTANT RULES:
- Use real uuid4 values for all id fields (template-, section-, question- prefixes).
- exportedAt and savedAt should be null (the system fills them).
- Every question MUST use the default 0-5 scale: likert.max = 5, likert.min = 0, threshold = 3, and the full six scalePoints shown above.
- The template.defaults scalePoints must be the same six-point scale.
- Each section may have children (nested sections) and/or questions, both arrays.
- Sections with no direct questions still need an empty questions array.
- The likert.scalePoints array must cover the full range from min to max.
- Do NOT include a "validation" key in the output.
- Do NOT include a "section_type", "section_name", "headers", or "rows" key.
- likertMax is the maximum value (5 for a 0-5 scale)."""

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
    Extracts title, standard, version, description, and sections directly from
    text content and emits the com.audito.checksheet nested format.
    """
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        lines = ["Document Checksheet"]

    title = "Checksheet Document"
    # Find the first sheet that is NOT a summary/metadata sheet; use its name as title
    sheet_names = re.findall(r"^===\s*Sheet:\s*([^=]+?)\s*===", content, flags=re.M)
    for name in sheet_names:
        clean_name = name.strip()
        if re.match(r"^(summary|overview|dashboard|scores?)\b", clean_name, re.I):
            continue
        title = clean_name
        break

    # Prefer an explicit title: line if present, or a metadata field
    for l in lines[:12]:
        stripped = l.strip()
        if stripped.lower().startswith("title:"):
            title = stripped.split(":", 1)[1].strip()
            break
    # Last resort: use the first non-metadata, non-outline line as the title
    if title == "Checksheet Document":
        for l in lines:
            stripped = l.strip()
            if not stripped:
                continue
            if re.match(r"^(standard|version|description|title)\s*:", stripped, re.I):
                continue
            if re.match(r"^\s*\d+[\.\)]?\s*[A-Za-z]", stripped):
                continue  # numbered outline item, not a title
            title = stripped
            break
    title = re.sub(r"^[=\-#\s]+|[=\-#\s]+$", "", title).strip() or "Checksheet Document"

    standard = None
    version = None
    description = None

    for l in lines[:10]:
        if re.match(r"^standard\s*:", l, re.I):
            standard = l.split(":", 1)[1].strip()
        elif re.match(r"^version\s*:", l, re.I):
            version = l.split(":", 1)[1].strip()
        elif re.match(r"^description\s*:", l, re.I):
            description = l.split(":", 1)[1].strip()

    # Fall back to the default BEC 1500 template metadata if not found in content
    if not standard:
        standard = DEFAULT_STANDARD
    if not version:
        version = DEFAULT_VERSION

    # Default six-point BEC 1500 likert scale (0-5)
    default_scale = _default_scale_points()
    default_likert = {"min": DEFAULT_LIKERT_MIN, "max": DEFAULT_LIKERT_MAX, "scalePoints": default_scale}

    def _make_question(title_text: str, help_text: str = "") -> dict:
        return {
            "id": f"question-{_uuid4()}",
            "title": title_text,
            "helpText": help_text,
            "type": "likert_observation",
            "required": True,
            "evidenceRequired": True,
            "weight": 1,
            "threshold": DEFAULT_THRESHOLD,
            "likert": {**default_likert, "scalePoints": [dict(sp) for sp in default_scale]},
        }

    def _make_section(sec_title: str, sec_desc: str = "", code: str = "") -> dict:
        return {
            "id": f"section-{_uuid4()}",
            "code": code,
            "title": sec_title,
            "description": sec_desc,
            "weight": 1,
            "children": [],
            "questions": [],
        }

    # Build sections. Two content shapes are supported:
    #   A) Multi-sheet dumps: "=== Sheet: NAME ===" markers (xlsx extraction)
    #   B) Outline text: numbered headings + sub-numbered items (docx / plain text)
    sheet_parts = re.split(r"^===\s*Sheet:\s*", content, flags=re.M)
    sections = []

    def _add_part_sections(part_body_lines, part_name=None):
        """Extract questions from a body of lines.

        Returns a list of (section, question_texts) or directly mutates sections.
        Supports both flat numbered rows (sheet dumps) and outline numbering.
        """
        nonlocal sections
        if not part_body_lines:
            return

        # Detect outline style: any "X.Y" numbered item (e.g. "1.1 Question")
        outline = any(re.match(r"^\s*\d+\.\d+[\.\)\s]", l) for l in part_body_lines)

        if outline:
            # Numbered outline: "1. Heading" -> section, "1.1 Question" -> question
            current = None
            for line in part_body_lines:
                sec_m = re.match(r"^\s*(\d+)[\.\)]?\s+([A-Za-z].*)$", line)
                q_m = re.match(r"^\s*\d+\.\d+(\.\d+)*[\.\)]?\s+([A-Za-z].*)$", line)
                if q_m:
                    q_text = q_m.group(2).strip()
                    if current is None:
                        current = _make_section(part_name or "Section 1")
                    current["questions"].append(_make_question(q_text))
                elif sec_m:
                    if current is not None:
                        sections.append(current)
                    current = _make_section(sec_m.group(2).strip(), code=sec_m.group(1))
            if current is not None:
                sections.append(current)
            return

        # Flat numbered rows (pandas to_string sheet dump)
        sec = _make_section(part_name or "Section 1", code="")
        question_texts = []
        for line in part_body_lines:
            m = re.match(r"^\s*(\d{1,4})[\.\s)\]]+\s*(.+)$", line)
            if not m:
                continue
            # pandas to_string pads columns with large whitespace runs; the question
            # text is the first column group after the row number.
            chunks = re.split(r"\s{3,}", m.group(2).strip())
            q_text = chunks[0].strip() if chunks else ""
            # Skip scale/label rows (long descriptions spanning the rating columns)
            if not q_text or len(q_text) > 400:
                continue
            if re.fullmatch(r"\d+(\.\d+)?", q_text) or re.fullmatch(r"[0-9.%\-]+", q_text):
                continue  # numeric-only cells (scores) are not questions
            question_texts.append(q_text)

        # Deduplicate while preserving order
        seen = set()
        for q_text in question_texts:
            key = q_text.lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            sec["questions"].append(_make_question(q_text))

        sections.append(sec)

    # ── A) Sheet-marker content (xlsx) ───────────────────────────────────────
    has_sheet_markers = len(sheet_parts) > 1
    for idx, part in enumerate(sheet_parts):
        if idx == 0:
            continue  # content before first sheet marker
        sheet_name = part.splitlines()[0].strip().strip("=").strip() or f"Section {idx}"
        # Skip pure-metadata summary sheets
        if re.match(r"^(summary|overview|dashboard|scores?)\b", sheet_name, re.I):
            continue
        body_lines = [l.strip() for l in part.splitlines()[1:] if l.strip()]
        _add_part_sections(body_lines, sheet_name)

    # ── B) Outline/plain content (docx, text, single block) ──────────────────
    if not has_sheet_markers:
        body_lines = [l.strip() for l in content.splitlines() if l.strip()]
        _add_part_sections(body_lines, None)

    if not sections:
        sections = [_make_section("Section 1")]

    template_id = f"template-{_uuid4()}"

    return {
        "schema": DEFAULT_SCHEMA,
        "schemaVersion": DEFAULT_SCHEMA_VERSION,
        "exportedAt": None,
        "savedAt": None,
        "appVersion": DEFAULT_APP_VERSION,
        "template": {
            "id": template_id,
            "title": title,
            "standard": standard,
            "version": version,
            "description": description,
            "defaults": {
                "questionType": "likert_observation",
                "likertMin": DEFAULT_LIKERT_MIN,
                "likertMax": DEFAULT_LIKERT_MAX,
                "required": True,
                "evidenceRequired": True,
                "weight": 1,
                "threshold": DEFAULT_THRESHOLD,
                "scalePoints": default_scale,
            },
            "sections": sections,
            "sectionNumberingTypes": [
                "numeric",
                "upper_alpha",
                "lower_alpha",
                "lower_roman",
                "upper_roman",
            ],
        },
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
            "max_tokens": 8000,
            "timeout": 15.0,  # 15s timeout per provider to prevent Vercel 60s function limit
        }

        try:
            import asyncio
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        **completion_kwargs,
                        response_format={"type": "json_object"}
                    ),
                    timeout=12.0
                )
            except Exception as e:
                logger.debug(f"[{provider_name}] json_object response_format retry: {e}")
                response = await asyncio.wait_for(
                    client.chat.completions.create(**completion_kwargs),
                    timeout=12.0
                )

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
