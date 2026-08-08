import re

# Regex for matching administrative/meta label fields.
# We match case-insensitively. We match if the string is exactly the label,
# or if it starts with the label followed by a colon, dash, or pipe.
_ADMIN_META_LABELS = [
    r"client\s+site\s+name",
    r"site\s+coordinator\s+name",
    r"total\s+score",
    r"grade",
    r"effective\s+date",
    r"disclaimer",
    r"client\s+name",
    r"coordinator\s+name",
    r"site\s+coordinator",
    r"site\s+name",
    r"client",
    r"coordinator",
    r"auditor",
    r"audit\s+date",
    r"date",
    r"standard",
    r"version",
    r"description",
    r"title",
    r"document\s+title",
    r"check\s*sheet",
    r"sheet\s+type",
    r"audited\s+by",
    r"audit\s+type",
    r"purpose",
    r"site\s*/\s*area",
    r"area",
    r"line",
    r"machine\s*(id)?",
    r"department",
    r"dept",
    r"technician",
    r"shift",
    r"product",
    r"reference",
    r"form\s*(no\.?)?",
    r"doc(ument)?\s*(no\.?)?",
    # Add common spreadsheet/table header artifacts that might get treated as questions
    r"control\s+id",
    r"control\s+requirement",
    r"check\s+id",
    r"check\s+item",
    r"sr\.?\s*no",
    r"serial\s+no",
    r"serial\s+number",
    r"score",
    r"observed\s+score",
    r"max\s+score",
    r"%\s+score",
    r"percentage",
    r"remarks?",
    r"comments?",
    r"status",
    r"result",
    r"outcome",
    r"verdict",
    r"action",
    r"id",
    r"no\.?",
    r"item",
    r"maturity",
    r"evidence",
    r"section",
    r"check",
    r"question",
    r"column",
    r"criterion",
    r"criteria",
    r"audit",
    r"observation",
    r"metric",
]

_ADMIN_META_RE = re.compile(
    r"^\s*(?:" + "|".join(_ADMIN_META_LABELS) + r")\s*(?:[:\-|]|$)",
    re.I
)

def is_administrative_or_meta(text: str) -> bool:
    """Return True if the text looks like an administrative field or metadata label."""
    if not text:
        return True
    text_stripped = text.strip()
    # If the text is very short (e.g. less than 2 characters), it's not a valid question
    if len(text_stripped) < 2:
        return True
    return bool(_ADMIN_META_RE.match(text_stripped))


def is_clean_title(title: str) -> bool:
    """Return True if the title is clean (i.e. not containing table delimiters or admin fields)."""
    if not title:
        return False
    title_str = title.strip()
    if not title_str:
        return False
    # If it contains pipe, page boundaries, or sheet decorators, it is not clean
    if any(sep in title_str for sep in ("|", "--", "===", "Sheet:", "Form:")):
        return False
    # If it matches an administrative or metadata field, it is not clean
    if is_administrative_or_meta(title_str):
        return False
    # If it is too short or extremely long, it is probably not a clean title
    if len(title_str) < 4 or len(title_str) > 100:
        return False
    # If it looks like a generic title like "Section 1"
    if re.match(r"^section\s+\d+", title_str, re.I):
        return False
    return True


def clean_up_title(title: str) -> str:
    """Try to extract a clean title from a dirty/concatenated title string."""
    if not title:
        return ""
    # If it contains a pipe, try the split parts
    if "|" in title:
        parts = [p.strip() for p in title.split("|") if p.strip()]
        for p in parts:
            if is_clean_title(p):
                return p
    cleaned = re.sub(r"^[=\-#\s]+|[=\-#\s]+$", "", title).strip()
    return cleaned


def split_title_and_help_text(full_text: str) -> tuple[str, str]:
    """
    Splits a long instruction or text into a core title and help text.
    E.g. "Chemical Safety: Look for a documented process..."
    -> ("Chemical Safety", "Look for a documented process...")
    """
    full_text = (full_text or "").strip()
    if not full_text:
        return "", ""

    # Delimiters in order of priority
    # 1. Newline or tab
    for sep in ("\n", "\t"):
        if sep in full_text:
            parts = full_text.split(sep, 1)
            p1, p2 = parts[0].strip(), parts[1].strip()
            if p1 and p2:
                return p1, p2

    # 2. Colon (but avoid protocol names or when followed by numbers)
    if ":" in full_text:
        parts = full_text.split(":", 1)
        p1, p2 = parts[0].strip(), parts[1].strip()
        if p1 and p2 and len(p1) > 1 and len(p1) <= 60 and not p1.lower() in ("http", "https"):
            return p1, p2

    # 3. Dash surrounded by spaces
    for sep in (" - ", " – ", " — "):
        if sep in full_text:
            parts = full_text.split(sep, 1)
            p1, p2 = parts[0].strip(), parts[1].strip()
            if p1 and p2 and len(p1) <= 60:
                return p1, p2

    # 4. Period followed by space
    if ". " in full_text:
        parts = full_text.split(". ", 1)
        p1, p2 = parts[0].strip(), parts[1].strip()
        if p1 and p2 and len(p1) <= 70:
            return p1, p2

    return full_text, ""
