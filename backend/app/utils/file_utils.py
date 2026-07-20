"""File utility functions: sanitization, validation, size checks."""
import os
import re
import uuid
from pathlib import Path
from app.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".xlsx": "excel",
    ".xls": "excel",
    ".pdf": "pdf",
    ".docx": "docx",
}

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def sanitize_filename(filename: str) -> str:
    """Remove dangerous characters from filename."""
    name = os.path.basename(filename)
    name = re.sub(r"[^\w\s\-.]", "", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip("._")
    if not name:
        name = "unnamed"
    return name


def generate_safe_filename(original: str) -> str:
    """Generate a UUID-prefixed safe filename."""
    ext = Path(original).suffix.lower()
    uid = str(uuid.uuid4())[:8]
    safe_name = sanitize_filename(Path(original).stem)
    return f"{uid}_{safe_name}{ext}"


def get_file_type(filename: str) -> str:
    """Return the document type based on file extension."""
    ext = Path(filename).suffix.lower()
    return ALLOWED_EXTENSIONS.get(ext, "unknown")


def validate_file_extension(filename: str) -> bool:
    """Check if the file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


def validate_file_size(size_bytes: int) -> bool:
    """Check file does not exceed max allowed size."""
    return size_bytes <= settings.max_upload_size_bytes


def get_upload_path(safe_filename: str) -> str:
    """Return the full filesystem path for storing an upload."""
    settings.ensure_upload_dir()
    return os.path.join(settings.upload_dir, safe_filename)
