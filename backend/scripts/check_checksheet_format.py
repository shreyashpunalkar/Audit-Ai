#!/usr/bin/env python
"""
Check whether an Audit-Ai JSON export matches the com.audito.checksheet format spec.

Usage:
    python check_checksheet_format.py <path-to-json-file>

Exits 0 when ALL checks pass, 1 when any check fails.
Prints one line per check:  [PASS] description   or   [FAIL] description (detail)
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

# Expected constants (must match ai_engine.py / validator.py)
EXPECTED_SCHEMA = "com.audito.checksheet"
EXPECTED_SCHEMA_VERSION = "1.0.0"
EXPECTED_APP_VERSION = "0.1.0"
EXPECTED_STANDARD = "BEC 1500:2024"
EXPECTED_VERSION = "1.0"
EXPECTED_LIKERT_MIN = 0
EXPECTED_LIKERT_MAX = 5
EXPECTED_THRESHOLD = 3

EXPECTED_SCALE_LABELS = [
    "Not Established/ Not Addressed",
    "Only Intent demonstrated(e.g. verbally indirectly)",
    "Policy/ Process evidence  Available, but implementation is not seen. ",
    "Fair Implementation (not complete) seen for the process along with the process/ policy definition in all areas, no communication to stakeholders such as suppliers. ",
    "Implementation seen for the process along with the process/ policy definition in all areas, with  communication to stakeholders such as suppliers. ",
    "Maturity seen in Implementation  (More than 12 months or across multiple verticals/ Departments) internally and communicated to Stakeholders and stakeholder participation also seen. ",
]

EXPECTED_SECTION_NUMBERING = ["numeric", "upper_alpha", "lower_alpha", "lower_roman", "upper_roman"]

results = []  # (ok: bool, label: str)


def check(ok: bool, label: str, detail: str = ""):
    results.append((bool(ok), label + (f" — {detail}" if detail else "")))


def is_uuid4(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def walk_questions(sections):
    for sec in sections or []:
        if not isinstance(sec, dict):
            continue
        for q in sec.get("questions") or []:
            yield sec, q
        yield from walk_questions(sec.get("children"))


def validate(data: dict) -> list[tuple[bool, str]]:
    global results
    results = []

    # ── 1. Top-level metadata ────────────────────────────────────────────────
    check(data.get("schema") == EXPECTED_SCHEMA, "schema == com.audito.checksheet",
          repr(data.get("schema")))
    check(data.get("schemaVersion") == EXPECTED_SCHEMA_VERSION, "schemaVersion == 1.0.0",
          repr(data.get("schemaVersion")))
    check(data.get("appVersion") == EXPECTED_APP_VERSION, "appVersion == 0.1.0",
          repr(data.get("appVersion")))
    check(bool(data.get("exportedAt")), "exportedAt is a non-empty ISO timestamp",
          repr(data.get("exportedAt")))
    check(bool(data.get("savedAt")), "savedAt is a non-empty ISO timestamp",
          repr(data.get("savedAt")))
    check("validation" not in data, "no top-level 'validation' block")

    # ── 2. template ──────────────────────────────────────────────────────────
    tmpl = data.get("template") or {}
    check(isinstance(tmpl, dict), "template is an object")
    if not isinstance(tmpl, dict):
        return results

    check(isinstance(tmpl.get("id"), str) and tmpl["id"].startswith("template-")
          and is_uuid4(tmpl["id"][len("template-"):]),
          "template.id == 'template-<uuid4>'", repr(tmpl.get("id")))
    check(isinstance(tmpl.get("title"), str) and tmpl.get("title"), "template.title is a non-empty string",
          repr(tmpl.get("title")))
    # standard/version should be the document's own metadata (non-empty string),
    # falling back to the BEC 1500 defaults when the document does not declare any.
    check(isinstance(tmpl.get("standard"), str) and tmpl.get("standard"),
          "template.standard is a non-empty string", repr(tmpl.get("standard")))
    check(isinstance(tmpl.get("version"), str) and tmpl.get("version"),
          "template.version is a non-empty string", repr(tmpl.get("version")))
    check(tmpl.get("sectionNumberingTypes") == EXPECTED_SECTION_NUMBERING,
          "template.sectionNumberingTypes == [numeric, upper_alpha, lower_alpha, lower_roman, upper_roman]",
          repr(tmpl.get("sectionNumberingTypes")))

    # ── 3. template.defaults ─────────────────────────────────────────────────
    defaults = tmpl.get("defaults") or {}
    check(isinstance(defaults, dict), "template.defaults is an object")
    check(defaults.get("questionType") == "likert_observation",
          "defaults.questionType == likert_observation", repr(defaults.get("questionType")))
    check(defaults.get("likertMin") == EXPECTED_LIKERT_MIN, "defaults.likertMin == 0",
          repr(defaults.get("likertMin")))
    check(defaults.get("likertMax") == EXPECTED_LIKERT_MAX, "defaults.likertMax == 5",
          repr(defaults.get("likertMax")))
    check(defaults.get("threshold") == EXPECTED_THRESHOLD, "defaults.threshold == 3",
          repr(defaults.get("threshold")))
    check(defaults.get("required") is True, "defaults.required == true",
          repr(defaults.get("required")))
    check(defaults.get("evidenceRequired") is True, "defaults.evidenceRequired == true",
          repr(defaults.get("evidenceRequired")))

    def scale_ok(sp_list, ctx: str):
        if not isinstance(sp_list, list) or len(sp_list) != 6:
            check(False, f"{ctx}: scalePoints has exactly 6 items",
                  f"got {len(sp_list) if isinstance(sp_list, list) else type(sp_list)}")
            return
        bad = []
        for i, sp in enumerate(sp_list):
            if not isinstance(sp, dict):
                bad.append(f"idx {i}: not an object")
                continue
            if sp.get("value") != i:
                bad.append(f"idx {i}: value != {i}")
            if sp.get("label") != EXPECTED_SCALE_LABELS[i]:
                bad.append(f"idx {i}: label mismatch: {sp.get('label')!r}")
            if "guidance" not in sp:
                bad.append(f"idx {i}: missing 'guidance'")
            if sp.get("labelOverridden") is not False:
                bad.append(f"idx {i}: labelOverridden != false")
        check(not bad, f"{ctx}: scalePoints match the 6 BEC labels", "; ".join(bad))

    scale_ok(defaults.get("scalePoints"), "defaults")

    # ── 4. sections ──────────────────────────────────────────────────────────
    sections = tmpl.get("sections")
    check(isinstance(sections, list), "template.sections is an array")
    if isinstance(sections, list) and sections:
        sec = sections[0]
        check(isinstance(sec.get("id"), str) and sec.get("id", "").startswith("section-")
              and is_uuid4(sec.get("id", "")[len("section-"):]),
              "section.id == 'section-<uuid4>'", repr(sec.get("id")))
        for key in ("code", "title", "description", "weight", "children", "questions"):
            check(key in sec, f"section has '{key}' key")

    # ── 5. every question ────────────────────────────────────────────────────
    questions = list(walk_questions(sections))
    check(len(questions) > 0, "at least one question found", f"found {len(questions)}")
    for sec, q in questions:
        ok_id = isinstance(q.get("id"), str) and q["id"].startswith("question-") \
            and is_uuid4(q["id"][len("question-"):])
        check(ok_id, f"question.id == 'question-<uuid4>'", repr(q.get("id")))
        check(isinstance(q.get("title"), str) and q.get("title"), "question.title is non-empty",
              repr(q.get("title")))
        check("helpText" in q, "question has 'helpText'", repr(q.get("helpText")))
        check(q.get("type") == "likert_observation", "question.type == likert_observation",
              repr(q.get("type")))
        check(q.get("required") is True, "question.required == true", repr(q.get("required")))
        check(q.get("evidenceRequired") is True, "question.evidenceRequired == true",
              repr(q.get("evidenceRequired")))
        check(q.get("threshold") == EXPECTED_THRESHOLD, "question.threshold == 3",
              repr(q.get("threshold")))

        likert = q.get("likert") or {}
        check(likert.get("min") == EXPECTED_LIKERT_MIN, "question.likert.min == 0",
              repr(likert.get("min")))
        check(likert.get("max") == EXPECTED_LIKERT_MAX, "question.likert.max == 5",
              repr(likert.get("max")))
        scale_ok(likert.get("scalePoints"), "question.likert")

    return results


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python check_checksheet_format.py <path-to-json>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"[FAIL] file not found: {path}")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[FAIL] invalid JSON: {e}")
        return 1

    validate(data)
    failed = [r for r in results if not r[0]]
    for ok, label in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    print("-" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
