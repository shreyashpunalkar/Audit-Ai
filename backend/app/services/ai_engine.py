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
from app.services.parser_utils import (
    is_administrative_or_meta,
    is_clean_title,
    split_title_and_help_text,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_SCHEMA = "com.audito.checksheet"
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_APP_VERSION = "0.1.0"
# Standard / version must come from the document ONLY. Never fabricate a standard
# code (this previously hallucinated "BEC 1500:2024" into every output).
DEFAULT_STANDARD = None
DEFAULT_VERSION = None
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
- TITLE: template.title must be the main document heading, verbatim. STRIP extraction artifacts from the title: a leading "Sheet:", "Form:", "=== Page N ===", "-- Table N --", or dash/equals/hash decoration.
- NEVER use table headers (e.g. containing "Client Site Name", "Sr. No", "Score", "Maturity", "Control ID", etc.) or administrative field names as the document title. If no clean, actual document title can be parsed, set template.title to "Audit Checksheet".
- standard / version: read ONLY from metadata lines such as "Standard: X" or "Version: X". If the document does NOT state a standard or version, set standard = null and version = null. NEVER invent, guess, or default a standard code or version number.
- description: an intro paragraph if present, otherwise null.

--- 2. QUESTIONS & FILTERS ---
- EVERY data row in a table or list in the document is EXACTLY ONE question, UNLESS it represents an administrative or metadata field.
- FILTER OUT administrative and metadata fields: Do NOT create questions for administrative cells or rows. Specifically, identify and exclude fields like "Client Site Name", "Site Coordinator Name", "Total Score", "Grade", "Effective Date", and "Disclaimer". These must NOT appear in the questions array. If they contain metadata values, they may be mapped to the top-level metadata object instead.
- For valid question rows:
  - The descriptive text column - the one whose text reads like an audit question or requirement (commonly headed "Control Requirement", "Requirement", "Check", "Question", "Description", or the longest text column) - becomes question.title and question.helpText.
  - If the descriptive text contains a core subject followed by long instructional sentences or details (commonly separated by a colon, dash, or period, e.g. "Chemical Safety: Look for a documented process for chemical safety..."), map the core subject (e.g. "Chemical Safety") to question.title and the long instructional/explanatory sentences (e.g. "Look for a documented process for chemical safety...") to question.helpText. If no separate subject exists, put the full text in question.title and leave helpText empty.
  - Do not paraphrase.
- DO NOT skip, merge, or drop any valid audit question row.
- Example mapping:
  Input row:  FS-01 | Fire | Are fire extinguishers inspected monthly and tagged with inspection dates? | 4 | Documented
  Output:     {"id": "question-<uuid4>", "title": "Are fire extinguishers inspected monthly and tagged with inspection dates?", "helpText": "", "type": "likert_observation", "required": true, "evidenceRequired": true, "weight": 1, "threshold": 3, "likert": { "min": 0, "max": 5, "scalePoints": [ same six points as defaults below ] }}
  
  Input row:  Chemical Safety: Look for a documented process for chemical safety. Ensure MSDS sheets are available. | 3 | Checked
  Output:     {"id": "question-<uuid4>", "title": "Chemical Safety", "helpText": "Look for a documented process for chemical safety. Ensure MSDS sheets are available.", "type": "likert_observation", "required": true, "evidenceRequired": true, "weight": 1, "threshold": 3, "likert": { "min": 0, "max": 5, "scalePoints": [ same six points as defaults below ] }}

- Each question gets a real uuid4 ("question-<uuid4>"). Questions have no "code" field; row/control IDs such as "FS-01" may be omitted or folded into helpText.

--- 3. SECTIONS ---
- Group questions under sections built from the document headings: top-level headings become sections, sub-headings become section children.
- Each section: id ("section-<uuid4>"), code, title, description, weight, children, questions.
- If the document has no explicit headings, put ALL questions in ONE section titled after the checksheet name, or "Section 1".

--- 4. SCALE ---
- Use the DEFAULT six-point BEC 1500 scale (0-5) below as template.defaults.scalePoints.
- Copy the SAME six scalePoints verbatim into EVERY question's likert.scalePoints. Every question: likert.min = 0, likert.max = 5, threshold = 3, type = "likert_observation", required = true, evidenceRequired = true, weight = 1.
- If the document explicitly defines its own rating labels, use those instead (still six points 0-5).

--- 5. CHECK RESULTS & METADATA ---
- If the document has a per-item result column (headed e.g. Result / Status / Score / Outcome / Verdict) and/or a remarks/comments column, ALSO emit a top-level "checkResults" array with EXACTLY ONE entry per question, in the same order as the questions:
  {"questionId": "<id of the matching question>", "result": "<verbatim result value or null>", "remark": "<verbatim remark value or null>"}
- Copy result and remark values VERBATIM (e.g. "Pass", "Fail", "NA", "4", "Compliant"). Leave a field null when the document has no value there.
- If the document has no per-item results, emit "checkResults": [].
- Also emit a top-level "metadata" object capturing header/field values found in the document (e.g. Auditor, Date, Site / Area, Line, Machine ID, Product, Reference, Dept, Shift, Technician, Audit Type). Include ONLY keys actually present; never invent values.

--- 6. SECTIONS (PRESERVE STRUCTURE) ---
- Keep the document's own heading hierarchy. Each named category/section heading from the document becomes its OWN top-level section titled verbatim. Do NOT flatten everything into one "Section 1" when the document has named headings.
{
  "schema": "com.audito.checksheet",
  "schemaVersion": "1.0.0",
  "exportedAt": null,
  "savedAt": null,
  "appVersion": "0.1.0",
  "template": {
    "id": "template-<uuid4>",
    "title": "Exact Main Heading from Document",
    "standard": null,
    "version": null,
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
  },
  "checkResults": [
    {
      "questionId": "question-<uuid4>",
      "result": "Pass",
      "remark": null
    }
  ],
  "metadata": {
    "Audit Type": "Safety",
    "Site / Area": "Production Line A"
  }
}

IMPORTANT RULES:
- Real uuid4 values for all id fields (template-, section-, question- prefixes).
- exportedAt and savedAt must be null (the system fills them).
- template.defaults.scalePoints is the six-point BEC 1500 scale shown above.
- Every question's likert.scalePoints must be the identical six-point scale, copied verbatim.
- standard and version are null unless explicitly stated in the document.
- "checkResults" and "metadata" are OPTIONAL top-level keys: include them exactly as described in Section 5, with one checkResults entry per question when results exist.
- Preserve section headings verbatim from the document (Section 6).
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
    r"^(no\.?|item|control|requirement|maturity|evidence|section|status|check|question|id|score|"
    r"weight|remarks?|column|criterion|criteria|result|outcome|verdict|audit|observation|metric)\b",
    re.I,
)

# Looser variant: match header words anywhere in the cell text (not just at
# the start). Used by _is_header_row to catch "Observed Score", "Max Score",
# "Status", etc. where the keyword is not the first word.
_HEADER_CELL_RE = re.compile(
    r"\b(no\.?|item|control|requirement|maturity|evidence|section|status|check|question|id|score|"
    r"weight|remarks?|column|criterion|criteria|result|outcome|verdict|audit|observation|metric)\b",
    re.I,
)

# Metadata field labels. These appear in checksheet headers ("Audit Type: Safety",
# "Site / Area | Production Line A", "Standard | BEC 1500:2024") and must be
# captured as metadata instead of leaking into questions.
_META_KEY_RE = re.compile(
    r"^(standard|version|description|title|document\s*title|check\s*sheet|sheet\s*type|"
    r"auditor|audited\s*by|audit\s*type|audit\s*date|date|purpose|site(\s*/\s*area)?|area|"
    r"line|machine(\s*id)?|department|dept|technician|shift|product|reference|"
    r"form(\s*no\.?)?|doc(ument)?(\s*no\.?)?)$",
    re.I,
)


def _is_meta_key(key) -> bool:
    """True when a header cell looks like a metadata field name (optionally with colon)."""
    k = (key or "").strip().rstrip(":").strip().lower()
    return bool(k) and bool(_META_KEY_RE.match(k))


def _is_meta_row(line: str) -> bool:
    """True when a line is a metadata row (colon or pipe-separated key/value pairs)."""
    parts = [p.strip() for p in re.split(r"[|;]", line) if p.strip()]
    if not parts:
        return False
    return _is_meta_key(parts[0].rstrip(":").strip())


def _is_header_row(cells) -> bool:
    """True when most meaningful cells in a pipe row look like column headers.

    Uses the looser _HEADER_CELL_RE (match anywhere in cell) and requires ≥50%
    of meaningful (non-numeric, non-empty) cells to match, so rows like
    "Client Site Name | Sr. No | Score | Observed Score | Max Score | % Score"
    are correctly detected as headers even though "Client Site Name" itself
    does not contain a header keyword.
    """
    meaningful = [c for c in cells if c and not re.fullmatch(r"[0-9\-\.,\s]+", c)]
    if not meaningful:
        return False
    hits = sum(1 for c in meaningful if _HEADER_CELL_RE.search(c))
    return hits >= len(meaningful) / 2


# Patterns for mapping header cells to column roles (question / result / remark)
_HEADER_COL_Q_RE = re.compile(
    r"^(control|requirement|check|question|description|criterion|criteria|item|audit|observation)", re.I
)
_HEADER_COL_RESULT_RE = re.compile(
    r"^(result|status|score|outcome|verdict|complian)", re.I
)
_HEADER_COL_REMARK_RE = re.compile(
    r"^(remark|comment|note|action)", re.I
)
_RESULT_TOKEN_RE = re.compile(
    r"^(pass|fail|na|n/a|yes|no|ok|compliant|non[ -]?compliant|met|not\s*met|conform|non[ -]?conform|open|closed|acceptable|reject|partial)\b",
    re.I,
)


def _map_header_columns(cells) -> dict:
    """Map header cells to (q, result, remark) column indices. -1 = not found."""
    mapping = {"q": -1, "result": -1, "remark": -1}
    for i, c in enumerate(cells):
        c = c.strip(" .").lower()
        if re.fullmatch(r"(no|s\.?no|sr|sn|#)", c):
            continue
        if mapping["result"] == -1 and _HEADER_COL_RESULT_RE.match(c):
            mapping["result"] = i
        elif mapping["remark"] == -1 and _HEADER_COL_REMARK_RE.match(c):
            mapping["remark"] = i
        elif mapping["q"] == -1 and _HEADER_COL_Q_RE.match(c):
            mapping["q"] = i
    return mapping


def _parse_data_row(cells, mapping) -> tuple:
    """Return (title, result, remark) for a data row using the header column mapping."""
    title = result = remark = None

    if mapping["q"] != -1 and mapping["q"] < len(cells):
        cand = cells[mapping["q"]].strip()
        if len(cand) >= 2 and not re.fullmatch(r"[0-9.,%\-/: ]+", cand):
            title = cand
    if title is None:
        title = _pick_question_cell(cells)

    if mapping["result"] != -1 and mapping["result"] < len(cells):
        result = cells[mapping["result"]].strip() or None
    elif title:
        for c in reversed(cells):
            if _RESULT_TOKEN_RE.match(c.strip()):
                result = c.strip()
                break

    if mapping["remark"] != -1 and mapping["remark"] < len(cells):
        remark = cells[mapping["remark"]].strip() or None
    elif result is not None and mapping["result"] != -1 and mapping["result"] + 1 < len(cells):
        rem = cells[mapping["result"] + 1].strip()
        if rem and rem != result:
            remark = rem

    return title, result, remark


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
    if best is not None:
        return best
    # Fallback for short/code rows (e.g. "C0-0 | Pending"): pick the first cell
    # that is not purely numeric, not a result token, and not a metadata key.
    for c in cells:
        c = c.strip()
        if not c:
            continue
        if re.fullmatch(r"[0-9.,%\-/: ]+", c):
            continue
        if _RESULT_TOKEN_RE.match(c):
            continue
        if _is_meta_key(c):
            continue
        if _HEADER_WORD_RE.match(c) and len(c) < 20:
            continue
        return c
    return None


def _extract_title(lines) -> str:
    """Extract a clean document title from the first meaningful line."""
    for l in lines[:15]:
        s = l.strip()
        if not s:
            continue
        if _is_meta_row(s):
            continue
        if "|" in s:
            continue  # table row — not a document title
        if re.match(r"^section\s+\d+", s, re.I):
            continue
        if re.match(r"^page\s+\d+", s, re.I):
            continue
        if re.match(r"^--\s*table\b", s, re.I):
            continue
        cleaned = re.sub(r"^[=\-#\s]+|[=\-#\s]+$", "", s).strip()
        m = re.match(r"^(?:sheet|form|page)\s*[:\-]\s*(.+)$", cleaned, re.I)
        if m:
            cleaned = m.group(1).strip()
        if is_clean_title(cleaned):
            return cleaned
    return "Audit Checksheet"


def _extract_metadata(lines):
    """Return (standard, version, description, metadata) from header lines.

    `metadata` is a dict of every metadata key/value pair found (e.g.
    {"Audit Type": "Safety", "Site / Area": "Production Line A"}), so header
    fields no longer leak into the questions list. standard/version/description
    default to None unless the document states them.
    """
    standard = version = description = None
    metadata = {}
    for l in lines[:25]:
        s = l.strip()
        if not s:
            continue
        parts = [p.strip() for p in re.split(r"[|;]", s) if p.strip()]
        i = 0
        while i < len(parts):
            p = parts[i]
            key = val = None
            # Colon form: "Key: Value"
            m = re.match(r"^([^:]+):\s*(.+)$", p)
            if m and _is_meta_key(m.group(1).strip()):
                key, val = m.group(1).strip(), m.group(2).strip()
            # Pipe form: "Key | Value"
            elif _is_meta_key(p.rstrip(":").strip()) and i + 1 < len(parts):
                nxt = parts[i + 1].strip()
                if not _is_meta_key(nxt.rstrip(":").strip()):
                    key, val = p.rstrip(":").strip(), nxt
                    i += 1  # consume the paired value part too
            if key and val:
                lkey = key.lower()
                if lkey == "standard" and not standard:
                    standard = val
                elif lkey == "version" and not version:
                    version = val
                elif lkey == "description" and not description:
                    description = val
                metadata[key] = val
            i += 1
    return standard, version, description, metadata


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
        if _is_meta_row(s):
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
    nested format with real sections, metadata, and checkResults.
    """
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    title = _extract_title(lines)
    standard, version, description, metadata = _extract_metadata(lines)

    default_scale = _default_scale_points()
    default_likert = {"min": DEFAULT_LIKERT_MIN, "max": DEFAULT_LIKERT_MAX, "scalePoints": default_scale}

    def _make_question(title_text: str) -> dict:
        q_title, q_help = split_title_and_help_text(title_text)
        return {
            "id": f"question-{_uuid4()}",
            "title": q_title,
            "helpText": q_help,
            "type": "likert_observation",
            "required": True,
            "evidenceRequired": True,
            "weight": 1,
            "threshold": DEFAULT_THRESHOLD,
            "likert": {**default_likert, "scalePoints": [dict(sp) for sp in default_scale]},
        }

    # Pre-classify lines: metadata rows and table header rows
    is_meta = [False] * len(lines)
    is_header = [False] * len(lines)
    col_maps = [None] * len(lines)
    for i, s in enumerate(lines):
        if _is_meta_row(s):
            is_meta[i] = True
            continue
        if "|" in s:
            cells = [c.strip() for c in s.split("|") if c.strip()]
            if _is_header_row(cells):
                is_header[i] = True
                col_maps[i] = _map_header_columns(cells)

    sections = []
    cur_section = None
    cur_mapping = {"q": -1, "result": -1, "remark": -1}
    seen_q = set()
    check_results = []
    has_result_col = False

    def add_question(title_text, qid):
        nonlocal cur_section
        # Filter administrative/metadata fields
        if is_administrative_or_meta(title_text):
            return False
        
        q_title, q_help = split_title_and_help_text(title_text)
        if is_administrative_or_meta(q_title):
            return False

        key = q_title.lower()[:80]
        if key in seen_q:
            return False
        seen_q.add(key)
        if cur_section is None:
            cur_section = {
                "id": f"section-{_uuid4()}",
                "code": "",
                "title": "Section 1",
                "description": "",
                "weight": 1,
                "children": [],
                "questions": [],
            }
            sections.append(cur_section)
        q_obj = _make_question(title_text)
        q_obj["id"] = qid
        cur_section["questions"].append(q_obj)
        return True

    def new_section(name):
        nonlocal cur_section
        cur_section = {
            "id": f"section-{_uuid4()}",
            "code": "",
            "title": name,
            "description": "",
            "weight": 1,
            "children": [],
            "questions": [],
        }
        sections.append(cur_section)

    for i, s in enumerate(lines):
        if is_meta[i]:
            continue
        if is_header[i]:
            cur_mapping = col_maps[i]
            if cur_mapping["result"] != -1 or cur_mapping["remark"] != -1:
                has_result_col = True
            continue
        if "|" in s:
            # Pipe row → data row
            cells = [c.strip() for c in s.split("|") if c.strip()]
            if not cells:
                continue
            q_title, result, remark = _parse_data_row(cells, cur_mapping)
            if q_title and len(q_title) >= 2 and not re.fullmatch(r"[0-9.,%\-/: ]+", q_title):
                qid = f"question-{_uuid4()}"
                if add_question(q_title, qid):
                    # One checkResults entry per question whenever the document
                    # has a result/remark column (blank cells become null).
                    if has_result_col:
                        check_results.append({
                            "questionId": qid,
                            "result": result or None,
                            "remark": remark or None,
                        })
            continue
        # Non-pipe line: might be a section heading or an explicit "Section N" marker
        # Explicit section heading: short, non-numeric, non-title, and the NEXT
        # non-meta line is a header row (category label above its table).
        nxt = i + 1
        while nxt < len(lines) and is_meta[nxt]:
            nxt += 1
        if (len(s) <= 80
                and not re.fullmatch(r"[0-9\-\.,\s]+", s)
                and s.lower() != title.lower()
                and nxt < len(lines) and is_header[nxt]):
            new_section(s)
            continue
        # "Section N" / "Section N: Title" (no header following)
        m = re.match(r"^section\s+(\d+)\s*[:\-\.]?\s*(.*)$", s, re.I)
        if m:
            sec_name = f"Section {m.group(1)}"
            if m.group(2).strip():
                sec_name = f"Section {m.group(1)}: {m.group(2).strip()}"
            new_section(sec_name)
            continue

    # Drop empty sections
    sections = [sec for sec in sections if sec["questions"]]
    if not sections:
        new_section("Section 1")

    template_id = f"template-{_uuid4()}"

    res = {
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
    if check_results:
        res["checkResults"] = check_results
    if metadata:
        res["metadata"] = metadata
    return res


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
