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
    Apply auto-corrections to common AI output issues.
    """
    data = _coerce_values(data)

    # Ensure template is a dict
    if "template" not in data or data["template"] is None:
        data["template"] = {
            "id": "",
            "title": "",
            "sections": []
        }

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

    # Step 1: Auto-correct common issues
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

    # Step 3: Hard validation count check if present
    validation = corrected.get("validation")
    if isinstance(validation, dict):
        rows_detected = validation.get("rows_detected", 0)
        rows_extracted = validation.get("rows_extracted", 0)
        columns_detected = validation.get("columns_detected", 0)
        columns_extracted = validation.get("columns_extracted", 0)
        sections_detected = validation.get("sections_detected", 0)
        sections_extracted = validation.get("sections_extracted", 0)
        checklist_items_detected = validation.get("checklist_items_detected", 0)
        checklist_items_extracted = validation.get("checklist_items_extracted", 0)

        # Throw a hard ValueError if there is a mismatch
        if (
            rows_detected != rows_extracted or
            columns_detected != columns_extracted or
            sections_detected != sections_extracted or
            checklist_items_detected != checklist_items_extracted
        ):
            raise ValueError("Incomplete extraction")

    return corrected, errors


def serialize_json(data: dict) -> str:
    """Serialize dict to formatted JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False)
