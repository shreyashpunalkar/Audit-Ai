"""
JSON schema validation service.

Validates AI-generated JSON against the com.audito.checksheet schema using jsonschema.
Provides auto-correction of common formatting issues.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from jsonschema import Draft7Validator, ValidationError, SchemaError

logger = logging.getLogger(__name__)

# ─── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_SCHEMA = "com.audito.checksheet"
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_APP_VERSION = "0.1.0"
# These must come from the document only. Do not fabricate a standard or version.
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

# ─── Checksheet JSON Schema (com.audito.checksheet) ───────────────────────────

CHECKSHEET_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AuditoChecksheet",
    "type": "object",
    "required": ["schema", "schemaVersion", "template"],
    "properties": {
        "schema": {"type": "string"},
        "schemaVersion": {"type": "string"},
        "exportedAt": {"type": ["string", "null"]},
        "savedAt": {"type": ["string", "null"]},
        "appVersion": {"type": ["string", "null"]},
        "template": {
            "type": "object",
            "required": ["id", "title", "sections"],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "standard": {"type": ["string", "null"]},
                "version": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "defaults": {"type": ["object", "null"]},
                "sections": {"type": "array"},
                "sectionNumberingTypes": {"type": "array"},
            }
        }
    },
    "additionalProperties": True
}

# Pre-compiled Draft7Validator once globally for maximum performance
_COMPILED_VALIDATOR = Draft7Validator(CHECKSHEET_SCHEMA)


# ─── Auto-Correction Helpers ──────────────────────────────────────────────────

def _coerce_values(obj: Any) -> Any:
    """Recursively coerce values safely."""
    if isinstance(obj, dict):
        return {k: _coerce_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_coerce_values(i) for i in obj]
    elif obj is None or isinstance(obj, (int, float, bool)):
        return obj
    else:
        return str(obj)


def _fix_id_prefix(raw_id: str, prefix: str) -> str:
    """Ensure an ID has the correct prefix. If missing or malformed, regenerate."""
    if raw_id and isinstance(raw_id, str) and raw_id.startswith(prefix):
        return raw_id
    return f"{prefix}{uuid.uuid4()}"


def _ensure_scale_points(min_val: int, max_val: int, existing: list | None = None) -> list[dict]:
    """Ensure scale points cover the full range min..max.

    When a full default 0..5 scale is needed and no source is provided, the BEC 1500
    maturity labels are used.
    """
    default_map = {sp["value"]: sp for sp in DEFAULT_SCALE_POINTS}
    points = []
    existing_map = {}
    if existing:
        for sp in existing:
            if isinstance(sp, dict) and "value" in sp:
                existing_map[sp["value"]] = sp

    for v in range(min_val, max_val + 1):
        if v in existing_map:
            sp = dict(existing_map[v])
        else:
            sp = dict(default_map.get(v, {"value": v, "label": "", "guidance": "", "labelOverridden": False}))
        sp.setdefault("label", "")
        sp.setdefault("guidance", "")
        sp.setdefault("labelOverridden", False)
        points.append(sp)
    return points


def _normalize_question(q: dict, defaults: dict) -> dict:
    """Normalize a single question to the com.audito.checksheet format."""
    if not isinstance(q, dict):
        return None

    q["id"] = _fix_id_prefix(q.get("id", ""), "question-")
    q.setdefault("title", "")
    q.setdefault("helpText", "")
    q.setdefault("type", defaults.get("questionType", "likert_observation"))
    q.setdefault("required", defaults.get("required", True))
    q.setdefault("evidenceRequired", defaults.get("evidenceRequired", True))
    q.setdefault("weight", defaults.get("weight", 1))
    q.setdefault("threshold", defaults.get("threshold", DEFAULT_THRESHOLD))

    # Normalize likert block (default 0-5 BEC scale)
    likert = q.get("likert")
    if not isinstance(likert, dict):
        likert = {}

    likert_min = likert.get("min", defaults.get("likertMin", DEFAULT_LIKERT_MIN))
    likert_max = likert.get("max", defaults.get("likertMax", DEFAULT_LIKERT_MAX))
    likert["min"] = likert_min
    likert["max"] = likert_max

    existing_sp = likert.get("scalePoints")
    if isinstance(existing_sp, list) and existing_sp:
        likert["scalePoints"] = _ensure_scale_points(likert_min, likert_max, existing_sp)
    else:
        # Try to take from defaults
        defaults_sp = defaults.get("scalePoints")
        if isinstance(defaults_sp, list) and defaults_sp:
            likert["scalePoints"] = _ensure_scale_points(likert_min, likert_max, defaults_sp)
        else:
            likert["scalePoints"] = _ensure_scale_points(likert_min, likert_max)

    q["likert"] = likert
    return q


def _normalize_section(sec: dict, defaults: dict, section_idx: int = 1) -> dict:
    """Recursively normalize a section and its children/questions."""
    if not isinstance(sec, dict):
        return None

    sec["id"] = _fix_id_prefix(sec.get("id", ""), "section-")
    sec.setdefault("code", "")
    sec.setdefault("title", f"Section {section_idx}")
    sec.setdefault("description", "")
    sec.setdefault("weight", 1)

    # Normalize children recursively
    children = sec.get("children")
    if not isinstance(children, list):
        children = []
    normalized_children = []
    for ci, child in enumerate(children, 1):
        normalized = _normalize_section(child, defaults, ci)
        if normalized:
            normalized_children.append(normalized)
    sec["children"] = normalized_children

    # Normalize questions
    questions = sec.get("questions")
    if not isinstance(questions, list):
        questions = []
    normalized_questions = []
    for q in questions:
        normalized = _normalize_question(q, defaults)
        if normalized:
            normalized_questions.append(normalized)
    sec["questions"] = normalized_questions

    return sec


def auto_correct(data: dict) -> dict:
    """
    Apply auto-corrections to common AI output formatting issues.
    Ensures output matches the com.audito.checksheet format exactly.
    """
    data = _coerce_values(data)

    if not isinstance(data, dict):
        data = {}

    # Remove validation block (should not be in com.audito.checksheet output)
    data.pop("validation", None)

    # Set correct schema constants
    data.setdefault("schema", DEFAULT_SCHEMA)
    data.setdefault("schemaVersion", DEFAULT_SCHEMA_VERSION)
    data.setdefault("appVersion", DEFAULT_APP_VERSION)

    # Fill timestamps if null
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    if not data.get("exportedAt"):
        data["exportedAt"] = now_iso
    if not data.get("savedAt"):
        data["savedAt"] = now_iso

    # Ensure template object exists and is valid
    if "template" not in data or not isinstance(data["template"], dict):
        data["template"] = {}

    tmpl = data["template"]

    # Auto-correct Title
    if not tmpl.get("title"):
        tmpl["title"] = "Checksheet Document"

    # Auto-correct ID (ensure template- prefix)
    tmpl["id"] = _fix_id_prefix(tmpl.get("id", ""), "template-")

    # Standard / version come from the document only — never fabricate them
    tmpl.setdefault("standard", None)
    tmpl.setdefault("version", None)
    tmpl.setdefault("description", None)

    # Ensure sectionNumberingTypes
    if "sectionNumberingTypes" not in tmpl or not isinstance(tmpl["sectionNumberingTypes"], list):
        tmpl["sectionNumberingTypes"] = [
            "numeric", "upper_alpha", "lower_alpha", "lower_roman", "upper_roman"
        ]

    # Ensure defaults exist (default 0-5 BEC scale)
    defaults = tmpl.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {
            "questionType": "likert_observation",
            "likertMin": DEFAULT_LIKERT_MIN,
            "likertMax": DEFAULT_LIKERT_MAX,
            "required": True,
            "evidenceRequired": True,
            "weight": 1,
            "threshold": DEFAULT_THRESHOLD,
            "scalePoints": _ensure_scale_points(DEFAULT_LIKERT_MIN, DEFAULT_LIKERT_MAX),
        }
    else:
        defaults.setdefault("questionType", "likert_observation")
        defaults.setdefault("likertMin", DEFAULT_LIKERT_MIN)
        defaults.setdefault("likertMax", DEFAULT_LIKERT_MAX)
        defaults.setdefault("required", True)
        defaults.setdefault("evidenceRequired", True)
        defaults.setdefault("weight", 1)
        defaults.setdefault("threshold", DEFAULT_THRESHOLD)
        likert_min = defaults.get("likertMin", DEFAULT_LIKERT_MIN)
        likert_max = defaults.get("likertMax", DEFAULT_LIKERT_MAX)
        existing_sp = defaults.get("scalePoints")
        if not isinstance(existing_sp, list) or not existing_sp:
            defaults["scalePoints"] = _ensure_scale_points(likert_min, likert_max)
        else:
            defaults["scalePoints"] = _ensure_scale_points(likert_min, likert_max, existing_sp)

    tmpl["defaults"] = defaults

    # Normalize sections recursively
    sections = tmpl.get("sections")
    if not isinstance(sections, list):
        sections = []

    normalized_sections = []
    for idx, sec in enumerate(sections, 1):
        normalized = _normalize_section(sec, defaults, idx)
        if normalized:
            normalized_sections.append(normalized)

    tmpl["sections"] = normalized_sections

    return data


# ─── Main Validator ───────────────────────────────────────────────────────────

def validate_checksheet_json(data: dict) -> tuple[dict, list[str]]:
    """
    Validate and auto-correct a checksheet JSON dict.

    Returns:
        (corrected_data, errors)
        errors is empty if validation passed.
    """
    errors = []

    # Step 1: Auto-correct common formatting issues
    corrected = auto_correct(data)

    # Step 2: Fast pre-compiled schema validation
    try:
        validation_errors = list(_COMPILED_VALIDATOR.iter_errors(corrected))
        for e in validation_errors:
            path_str = " -> ".join(str(p) for p in e.absolute_path)
            errors.append(f"Schema validation: {e.message} (path: {path_str})")
    except SchemaError as e:
        errors.append(f"Internal schema error: {e.message}")
    except Exception as e:
        errors.append(f"Unexpected validation error: {str(e)}")

    # Step 3: Content-quality checks
    tpl = corrected.get("template") or {}
    sections = tpl.get("sections") or []
    q_count = sum(len(s.get("questions") or []) for s in sections)
    if q_count == 0:
        errors.append("Quality: no questions were extracted from the document.")

    title = (tpl.get("title") or "").strip()
    if not title:
        errors.append("Quality: missing template title.")
    elif re.search(r"\||--\s*table|===\s*page|sheet\s*[:]|form\s*[:]|^\s*Section\s*\d", title, re.I):
        errors.append(f"Quality: title looks like an extraction artifact: {title!r}")

    dupes = _find_duplicate_questions(sections)
    if dupes:
        errors.append(f"Quality: {len(dupes)} duplicate question title(s).")

    cr = corrected.get("checkResults") or []
    if isinstance(cr, list) and cr:
        valid_ids = {q["id"] for s in sections for q in s.get("questions") or []}
        bad = [r.get("questionId") for r in cr if r.get("questionId") not in valid_ids]
        if bad:
            errors.append(f"Quality: {len(bad)} checkResult(s) reference unknown question IDs.")

    return corrected, errors


def _find_duplicate_questions(sections: list) -> list[str]:
    """Return a list of duplicate question titles (lowercased, first-80-chars key)."""
    seen = {}
    dupes = []
    for sec in sections:
        for q in sec.get("questions") or []:
            key = (q.get("title") or "")[:80].lower()
            if key in seen:
                dupes.append(key)
            else:
                seen[key] = True
    return dupes


def serialize_json(data: dict) -> str:
    """Serialize dict to formatted JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)
