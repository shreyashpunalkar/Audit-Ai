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
    Retains verbatim raw text, deduplicates consecutive identical blank lines.
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []
    empty_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            empty_count += 1
            if empty_count <= 2:  # Retain max 2 consecutive blank lines
                cleaned_lines.append("")
            continue

        empty_count = 0
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


# ─── Excel ────────────────────────────────────────────────────────────────────

def extract_excel(file_path: str) -> str:
    try:
        import pandas as pd
        xl = pd.ExcelFile(file_path)
        parts = []
        for sheet_name in xl.sheet_names:
            # header=None: do NOT treat row 1 as pandas column names (that produced
            # "Unnamed: N" header lines) and do NOT prepend the sheet tab name as the
            # document title. The document's own title row becomes the first line.
            df = xl.parse(sheet_name, header=None)
            df = df.dropna(how="all").fillna("")
            if df.empty:
                continue
            # First non-empty row is usually the merged title row -> emit it verbatim.
            title_cells = [str(c) for c in df.iloc[0].values if str(c).strip()]
            if title_cells:
                parts.append(" | ".join(title_cells))
            # Remaining rows: pipe-separated, preserving internal empty cells but
            # trimming trailing empties so rows stay clean for the parser.
            for _, row in df.iloc[1:].iterrows():
                cells = [str(v) for v in row.values]
                while cells and not cells[-1].strip():
                    cells.pop()
                if any(c.strip() for c in cells):
                    parts.append(" | ".join(cells))
        return clean_and_deduplicate_text("\n\n".join(parts))
    except Exception as e:
        logger.error(f"Excel extraction failed: {e}")
        raise RuntimeError(f"Excel extraction failed: {e}")


# ─── PDF ──────────────────────────────────────────────────────────────────────

def extract_pdf(file_path: str) -> str:
    try:
        # pyrefly: ignore [missing-import]
        import pdfplumber
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.find_tables()
                table_spans = [(t.bbox[1], t.bbox[3]) for t in tables]  # (top, bottom)

                # Non-table text only, tagged with their y-position so the two
                # passes below can be interleaved in true reading order.
                text_lines = []
                for line in page.extract_text_lines() or []:
                    top = line.get("top", 0)
                    if any(top >= t0 - 3 and top <= t1 + 3 for (t0, t1) in table_spans):
                        # Inside a table bbox — skip free-text copies; the clean
                        # pipe rows are emitted from extract_tables() below.
                        continue
                    text = (line.get("text") or "").strip()
                    if text:
                        text_lines.append((top, text))

                # Structured tables as (top, rows) — pipe rows preserve empty
                # cells so column positions stay aligned for question/result/remark
                # mapping. Reuse the find_tables() result so we also know each
                # table's y-position for the interleave below.
                table_items = []
                for table in tables:
                    rows = []
                    for row in table.extract() or []:
                        cells = ["" if cell is None else " ".join(str(cell).split()) for cell in row]
                        if any(c for c in cells):
                            rows.append(" | ".join(cells))
                    if rows:
                        table_items.append((table.bbox[1], rows))

                # Interleave by y-position: a category label printed just above its
                # table must appear immediately before that table's rows, otherwise
                # the parser cannot group rows under their section heading.
                items = [(top, "text", t) for top, t in text_lines]
                items += [(top, "table", rs) for top, rs in table_items]
                items.sort(key=lambda it: it[0])
                for _, kind, payload in items:
                    if kind == "text":
                        parts.append(payload)
                    else:
                        parts.extend(payload)
        return clean_and_deduplicate_text("\n".join(parts))
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise RuntimeError(f"PDF extraction failed: {e}")


# ─── DOCX ─────────────────────────────────────────────────────────────────────

def extract_docx(file_path: str) -> str:
    try:
        from docx import Document
        from docx.table import Table as _DocxTable
        from docx.text.paragraph import Paragraph as _DocxParagraph
        from docx.oxml.ns import qn
        doc = Document(file_path)
        parts = []

        # Iterate the body in document order so section headings interleave with
        # their tables (previously all paragraphs came first, then all tables,
        # which made it impossible to group rows under their headings).
        for child in doc.element.body.iterchildren():
            if child.tag == qn("w:p"):
                p = _DocxParagraph(child, doc)
                txt = p.text.strip()
                if txt:
                    parts.append(txt)
            elif child.tag == qn("w:tbl"):
                t = _DocxTable(child, doc)
                for row in t.rows:
                    cells = []
                    for cell in row.cells:
                        cell_txt = cell.text.strip()
                        cells.append(cell_txt)
                    # Keep internal empty cells (keeps column alignment for result /
                    # remark) but trim trailing empties.
                    while cells and not cells[-1]:
                        cells.pop()
                    if any(cells):
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
