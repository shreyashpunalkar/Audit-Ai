"""
Document content extraction service.

Handles: Excel (.xlsx/.xls), PDF (.pdf), PNG Images (.png), DOCX (.docx)
Returns a clean, plain-text representation of the document suitable for AI parsing.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Text Cleaning & Deduplication ───────────────────────────────────────────

def clean_and_deduplicate_text(text: str) -> str:
    """
    Clean extracted document text:
    1. Fixes stuttered/duplicated syllables (e.g. 'unobobstructed' -> 'unobstructed').
    2. Deduplicates repeated standalone words or consecutive identical lines.
    3. Truncates excessive empty lines and trailing blank blocks.
    """
    if not text:
        return ""

    # 1. Deduplicate repeated syllable patterns inside words (e.g. unobobstructed -> unobstructed)
    text = re.sub(r'([a-zA-Z]{2,5})\1+', r'\1', text)

    # 2. Deduplicate standalone repeated words (e.g. "table table")
    text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text, flags=re.IGNORECASE)

    # 3. Line-level deduplication and fast boundary trimming
    lines = text.splitlines()
    cleaned_lines = []
    prev_line = None
    empty_count = 0

    for line in lines:
        stripped = line.strip()

        if not stripped:
            empty_count += 1
            if empty_count <= 2:  # Retain max 2 consecutive blank lines
                cleaned_lines.append("")
            continue

        empty_count = 0

        # Skip duplicate consecutive identical lines
        if stripped == prev_line:
            continue

        prev_line = stripped
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


# ─── Excel ────────────────────────────────────────────────────────────────────

def extract_excel(file_path: str) -> str:
    try:
        import pandas as pd
        xl = pd.ExcelFile(file_path)
        parts = []
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            df = df.dropna(how="all").dropna(how="all", axis=1).fillna("")
            if not df.empty:
                parts.append(f"=== Sheet: {sheet_name} ===")
                parts.append(df.to_string(index=False))
        return clean_and_deduplicate_text("\n\n".join(parts))
    except Exception as e:
        logger.error(f"Excel extraction failed: {e}")
        raise RuntimeError(f"Excel extraction failed: {e}")


# ─── PDF ──────────────────────────────────────────────────────────────────────

def extract_pdf(file_path: str) -> str:
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                parts.append(f"=== Page {page_num} ===")
                tables = page.extract_tables()
                if tables:
                    for tbl_idx, table in enumerate(tables, 1):
                        parts.append(f"-- Table {tbl_idx} --")
                        for row in table:
                            cleaned = [str(cell or "").strip() for cell in row if cell]
                            if cleaned:
                                parts.append(" | ".join(cleaned))
                else:
                    text = page.extract_text()
                    if text:
                        parts.append(text)
        return clean_and_deduplicate_text("\n".join(parts))
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise RuntimeError(f"PDF extraction failed: {e}")


# ─── DOCX ─────────────────────────────────────────────────────────────────────

def extract_docx(file_path: str) -> str:
    try:
        from docx import Document
        doc = Document(file_path)
        parts = []

        for para in doc.paragraphs:
            txt = para.text.strip()
            if txt:
                parts.append(txt)

        for tbl_idx, table in enumerate(doc.tables, 1):
            parts.append(f"\n-- Table {tbl_idx} --")
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        return clean_and_deduplicate_text("\n".join(parts))
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        raise RuntimeError(f"DOCX extraction failed: {e}")


# ─── Dispatcher ───────────────────────────────────────────────────────────────

def extract_content(file_path: str, file_type: str) -> str:
    """
    Extract raw text content from the given file.

    Returns:
        content: str
    """
    if file_type == "excel":
        return extract_excel(file_path)
    elif file_type == "pdf":
        return extract_pdf(file_path)
    elif file_type == "docx":
        return extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
