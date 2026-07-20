"""Upload router — POST /api/upload"""
import os
import logging
import aiofiles
from fastapi import APIRouter, File, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentUploadResponse
from app.utils.file_utils import (
    validate_file_extension,
    validate_file_size,
    generate_safe_filename,
    get_file_type,
    get_upload_path,
)
from app.utils.error_handler import FileTooLargeError, UnsupportedFileTypeError
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["upload"])
settings = get_settings()


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a checksheet document for AI processing.
    Supports: .xlsx, .xls, .pdf, .png, .docx
    Max size: 25 MB
    """
    original_name = file.filename or "unnamed"

    # Validate extension
    if not validate_file_extension(original_name):
        from pathlib import Path
        ext = Path(original_name).suffix.lower()
        raise UnsupportedFileTypeError(ext)

    # Read file content to check size
    content = await file.read()
    size_bytes = len(content)

    if not validate_file_size(size_bytes):
        size_mb = size_bytes / (1024 * 1024)
        raise FileTooLargeError(size_mb, settings.max_upload_size_mb)

    # Generate safe filename and save
    safe_name = generate_safe_filename(original_name)
    file_path = get_upload_path(safe_name)
    file_type = get_file_type(original_name)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    logger.info(f"Uploaded: {original_name} → {safe_name} ({size_bytes} bytes)")

    # Persist to database
    doc = Document(
        original_filename=original_name,
        safe_filename=safe_name,
        file_type=file_type,
        file_size=size_bytes,
        file_path=file_path,
        status="uploaded",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    return DocumentUploadResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        message=f"File '{original_name}' uploaded successfully. Ready for processing.",
    )
