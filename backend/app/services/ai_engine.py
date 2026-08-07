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

SYSTEM_PROMPT = """You are an expert Document Intelligence Lead. Convert checksheet / audit-checklist document content into the target JSON schema with 100% literal data integrity.

--- 1. TITLE & METADATA ---
- TITLE: template.title must be the main document heading, verbatim. STRIP extraction artifacts from the title: a leading "Sheet:", "Form:", "=== Page N ===", "-- Table N --", or dash/equals/hash decoration. NEVER use "Page 1", "Sheet: ...", "Table 1", or a section marker as the title.
- standard / version: read from metadata lines such as "Standard: X" or "Version: X". If absent, standard = "BEC 1500:2024", version = "1.0".
- description: an intro paragraph if present, otherwise null.

--- 2. QUESTIONS (MOST IMPORTANT RULE) ---
- EVERY data row in a table or list in the document is EXACTLY ONE question. Convert each row into one question object.
- The descriptive text column - the one whose text reads like an audit question or requirement (commonly headed "Control Requirement", "Requirement", "Check", "Question", "Description", or the longest text column) - becomes question.title, verbatim. Do not paraphrase.
- DO NOT skip, merge, or drop any row. If the document has N data rows, output exactly N question objects.
- NEVER return an empty questions array when the document contains question rows. Every section that has questions must list ALL of them.
- Example mapping:
  Input row:  FS-01 | Fire | Are fire extinguishers inspected monthly and tagged with inspection dates? | 4 | Documented
  Output:     {"id": "question-<uuid4>", "title": "Are fire extinguishers inspected monthly and tagged with inspection dates?", "helpText": "", "type": "likert_observation", "required": true, "evidenceRequired": true, "weight": 1, "threshold": 3, "likert": { "min": 0, "max": 5, "scalePoints": [ same six points as defaults below ] }}
- Each question gets a real uuid4 ("question-<uuid4>"). Questions have no "code" field; row/control IDs such as "FS-01" may be omitted or folded into helpText.

--- 3. SECTIONS ---
- Group questions under sections built from the document headings: top-level headings become sections, sub-headings become section children.
- Each section: id ("section-<uuid4>"), code, title, description, weight, children, questions.
- If the document has no explicit headings, put ALL questions in ONE section titled after the checksheet name, or "Section 1".

--- 4. SCALE ---
- Use the DEFAULT six-point BEC 1500 scale (0-5) below as template.defaults.scalePoints.
- Copy the SAME six scalePoints verbatim into EVERY question's likert.scalePoints. Every question: likert.min = 0, likert.max = 5, threshold = 3, type = "likert_observation", required = true, evidenceRequired = true, weight = 1.
- If the document explicitly defines its own rating labels, use those instead (still six points 0-5).

--- SCHEMA FORMAT ---
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
    "description": null,
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
        "description": "",
        "weight": 1,
        "children": [],
        "questions": [
          {
            "id": "question-<uuid4>",
            "title": "Exact question text from the document",
            "helpText": "",
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
    "sectionNumberingTypes": ["numeric", "upper_alpha", "lower_alpha", "lower_roman", "upper_roman"]
  }
}

IMPORTANT RULES:
- Real uuid4 values for all id fields (template-, section-, question- prefixes).
- exportedAt and savedAt must be null (the system fills them).
- template.defaults.scalePoints is the six-point BEC 1500 scale shown above.
- Every question's likert.scalePoints must be the identical six-point scale, copied verbatim.
- Do NOT include a "validation", "section_type", "section_name", "headers", or "rows" key.
- Return ONLY the JSON object, no commentary."""

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


def _count_questions(template_json) -> int:
    """Count all questions (direct + nested in section children) in a checksheet JSON."""
    if not isinstance(template_json, dict):
        return 0
    tpl = template_json.get("template")
    if not isinstance(tpl, dict):
        return 0
    count = 0
    def walk(sections):
        nonlocal count
        if not isinstance(sections, list):
            return
        for s in sections:
            if not isinstance(s, dict):
                continue
            count += len(s.get("questions") or [])
            walk(s.get("children"))
    walk(tpl.get("sections"))
    return count


_HEADER_WORD_RE = re.compile(
    r"^(control|requirement|maturity|evidence|section|status|check|question|id|score|"
    r"weight|remarks?|column|criteria|audit|observation|metric)\b",
    re.I,
)


def _is_header_row(cells) -> bool:
    """True when every meaningful cell in a pipe row looks like a column header."""
    meaningful = [c for c in cells if c and not re.fullmatch(r"[0-9\-\.,\s]+", c)]
    if not meaningful:
        return False
    return all(_HEADER_WORD_RE.match(c) for c in meaningful)


def _pick_question_cell(cells):
    """Return the most question-like cell of a pipe row, or None."""
    best = None
    for c in cells:
        c = c.strip()
        if not c or len(c) < 10:
            continue
        if _HEADER_WORD_RE.match(c) and len(c) < 40:
            continue  # header-ish cell (e.g. "Maturity: 4")
        if re.fullmatch(r"[0-9.,%\-/: ]+", c):
            continue  # numeric / rating cell
        if best is None or len(c) > len(best):
            best = c
    return best


def _extract_title(lines) -> str:
    """Extract a clean document title from the first meaningful line."""
    for l in lines[:15]:
        s = l.strip()
        if not s:
            continue
        if re.match(r"^(standard|version|description|title|auditor|date|purpose)\s*[:|]", s, re.I):
            continue
        if re.match(r"^section\s+\d+", s, re.I):
            continue
        if re.match(r"^--\s*table\b", s, re.I):
            continue
        cleaned = re.sub(r"^[=\-#\s]+|[=\-#\s]+$", "", s).strip()
        m = re.match(r"^(?:sheet|form|page)\s*[:\-]\s*(.+)$", cleaned, re.I)
        if m:
            cleaned = m.group(1).strip()
        if cleaned:
            return cleaned
    return "Checksheet Document"


def _extract_metadata(lines):
    """Return (standard, version, description) from metadata lines."""
    standard = version = description = None
    for l in lines[:20]:
        s = l.strip()
        for part in re.split(r"[|;]", s):
            p = part.strip()
            m = re.match(r"^standard\s*[:\-]\s*(.+)$", p, re.I)
            if m and not standard:
                standard = m.group(1).strip()
            m = re.match(r"^version\s*[:\-]\s*(.+)$", p, re.I)
            if m and not version:
                version = m.group(1).strip()
            m = re.match(r"^description\s*[:\-]\s*(.+)$", p, re.I)
            if m and not description:
                description = m.group(1).strip()
    if not standard:
        standard = DEFAULT_STANDARD
    if not version:
        version = DEFAULT_VERSION
    return standard, version, description


def _extract_questions(lines):
    """Extract question-title strings from document lines (deduplicated, in order)."""
    questions = []
    seen = set()
    def add(q):
        q = (q or "").strip()
        if len(q) < 5:
            return
        if re.fullmatch(r"[0-9.,%\-/: ]+", q):
            return
        key = q.lower()[:80]
        if key in seen:
            return
        seen.add(key)
        questions.append(q)

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(standard|version|description|title|auditor|date|purpose)\s*[:|]", s, re.I):
            continue
        if re.match(r"^sheet\s*:", s, re.I):
            continue
        if re.match(r"^--\s*table\b", s, re.I):
            continue
        if re.match(r"^---?\s*$", s):
            continue
        # Pipe-separated table row (Excel / DOCX table / PDF row)
        if "|" in s:
            cells = [c.strip() for c in s.split("|") if c.strip()]
            if not cells:
                continue
            if _is_header_row(cells):
                continue
            q = _pick_question_cell(cells)
            if q:
                add(q)
            continue
        # Outline item "1.1 Question" / "1.1 Question text"
        m = re.match(r"^\s*\d+\.\d+(\.\d+)*[\.\)]?\s+(.+)$", s)
        if m:
            add(m.group(2))
            continue
        # Long numbered item "1. Long question text"
        m = re.match(r"^\s*\d+[\.\)]?\s+(.+)$", s)
        if m and len(m.group(1)) > 30:
            add(m.group(1))
    return questions


def _build_fallback_json(content: str) -> dict:
    """
    Deterministic fallback parser for the current extractor output formats
    (pipe-separated Excel/DOCX/PDF rows). Emits the exact com.audito.checksheet
    nested format and never returns empty questions when the content has rows.
    """
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    title = _extract_title(lines)
    standard, version, description = _extract_metadata(lines)
    questions = _extract_questions(lines)

    default_scale = _default_scale_points()
    default_likert = {"min": DEFAULT_LIKERT_MIN, "max": DEFAULT_LIKERT_MAX, "scalePoints": default_scale}

    def _make_question(title_text: str) -> dict:
        return {
            "id": f"question-{_uuid4()}",
            "title": title_text,
            "helpText": "",
            "type": "likert_observation",
            "required": True,
            "evidenceRequired": True,
            "weight": 1,
            "threshold": DEFAULT_THRESHOLD,
            "likert": {**default_likert, "scalePoints": [dict(sp) for sp in default_scale]},
        }

    section_title = "Section 1"
    for l in lines[:40]:
        m = re.match(r"^section\s+(\d+)\s*[:\-\.]?\s*(.*)$", l, re.I)
        if m:
            section_title = f"Section {m.group(1)}"
            if m.group(2).strip():
                section_title = f"Section {m.group(1)}: {m.group(2).strip()}"
            break

    section = {
        "id": f"section-{_uuid4()}",
        "code": "",
        "title": section_title,
        "description": "",
        "weight": 1,
        "children": [],
        "questions": [_make_question(q) for q in questions],
    }

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
            "sections": [section],
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

    # Deterministic extraction runs once (fast, no API cost) and acts as the
    # quality gate: if the AI under-extracts questions compared to the
    # deterministic parser, we use the deterministic result instead so the
    # caller never sees empty or missing questions.
    deterministic_result = _build_fallback_json(content)
    det_q = _count_questions(deterministic_result)
    logger.info(f"Deterministic extraction found {det_q} questions.")

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
            ai_q = _count_questions(result)
            logger.info(f"AI extraction via {provider_name} ({model_name}): {ai_q} questions.")

            # Quality gate: use AI result only if it extracted at least as many
            # questions as the deterministic parser (and >0). Otherwise the model
            # under-extracted and deterministic is more complete.
            if ai_q >= det_q and ai_q > 0:
                return result
            logger.warning(
                f"AI under-extracted ({ai_q} questions) vs deterministic ({det_q}). "
                f"Trying next provider or using deterministic result."
            )
            errors.append(f"{provider_name}: under-extracted ({ai_q} questions)")
            # Try next configured provider in failover loop!
            continue

        except Exception as err:
            logger.warning(f"AI extraction via {provider_name} ({model_name}) failed: {err}")
            errors.append(f"{provider_name}: {err}")
            # Try next configured provider in failover loop!
            continue

    logger.error(f"All AI providers failed or under-extracted ({errors}). Using deterministic extraction.")
    return deterministic_result
