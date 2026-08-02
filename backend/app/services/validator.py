"""
JSON schema validation service.

Validates AI-generated JSON against a checksheet schema using jsonschema.
Provides auto-correction of common formatting issues.
"""
import json
import logging
from typing import Any

from jsonschema import Draft7Validator, ValidationError, SchemaError

logger = logging.getLogger(__name__)

# ─── Checksheet JSON Schema ───────────────────────────────────────────────────

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
                "sections": {"type": "array"}
            }
        }
    },
    "additionalProperties": True
}

# Pre-compile Draft7Validator once globally for maximum performance
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


def auto_correct(data: dict) -> dict:
    """
    Apply auto-corrections to common AI output formatting issues.
    """
    data = _coerce_values(data)

    if not isinstance(data, dict):
        data = {}

    data.setdefault("schema", "https://auditai.com/schemas/checksheet.json")
    data.setdefault("schemaVersion", "1.0")
    data.setdefault("exportedAt", None)
    data.setdefault("savedAt", None)
    data.setdefault("appVersion", "1.0")

    # Ensure template object exists and is valid
    if "template" not in data or not isinstance(data["template"], dict):
        data["template"] = {}

    tmpl = data["template"]

    # Auto-correct Title
    if not tmpl.get("title"):
        tmpl["title"] = "Checksheet Document"

    # Auto-correct ID
    if not tmpl.get("id"):
        tmpl["id"] = re.sub(r"[^\w]+", "-", tmpl["title"].lower()).strip("-") or "checksheet-document"

    tmpl.setdefault("standard", None)
    tmpl.setdefault("version", None)
    tmpl.setdefault("description", None)
    tmpl.setdefault("defaults", None)

    # Auto-correct Sections
    if "sections" not in tmpl or not isinstance(tmpl["sections"], list):
        tmpl["sections"] = []

    total_rows = 0
    total_cols = 0
    total_checklist_items = 0

    for idx, sec in enumerate(tmpl["sections"], 1):
        if not isinstance(sec, dict):
            continue
        sec.setdefault("section_type", "table")
        if not sec.get("section_name"):
            sec["section_name"] = f"Section {idx}"
        if "headers" not in sec or not isinstance(sec["headers"], list):
            sec["headers"] = []
        if "rows" not in sec or not isinstance(sec["rows"], list):
            sec["rows"] = []

        num_rows = len(sec["rows"])
        total_rows += num_rows
        total_checklist_items += num_rows
        if sec["headers"]:
            total_cols = max(total_cols, len(sec["headers"]))

        # Auto-repair checkbox syntax in rows
        repaired_rows = []
        for row in sec["rows"]:
            if isinstance(row, list):
                repaired_cell_row = []
                for cell in row:
                    if isinstance(cell, str) and ("Pass" in cell or "Fail" in cell or "Yes" in cell or "No" in cell):
                        cell = re.sub(r'\[\s*(Pass|Fail|Yes|No|NA)\b', r'[ ] \1', cell, flags=re.IGNORECASE)
                        cell = re.sub(r'\[\]\s*(Pass|Fail|Yes|No|NA)\b', r'[ ] \1', cell, flags=re.IGNORECASE)
                    repaired_cell_row.append(cell)
                repaired_rows.append(repaired_cell_row)
            else:
                repaired_rows.append(row)
        sec["rows"] = repaired_rows

    # Auto-correct Validation Counts
    val = data.get("validation")
    if not isinstance(val, dict):
        val = {}

    num_secs = len(tmpl["sections"])
    val["sheets_detected"] = val.get("sheets_detected") or 1
    val["sheets_extracted"] = val.get("sheets_extracted") or 1
    val["sections_detected"] = num_secs
    val["sections_extracted"] = num_secs
    val["rows_detected"] = total_rows
    val["rows_extracted"] = total_rows
    val["columns_detected"] = total_cols or 4
    val["columns_extracted"] = total_cols or 4
    val["checklist_items_detected"] = total_checklist_items
    val["checklist_items_extracted"] = total_checklist_items

    data["validation"] = val
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

    return corrected, errors


def serialize_json(data: dict) -> str:
    """Serialize dict to formatted JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)
