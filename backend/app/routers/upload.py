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

    # Generate safe filename and target path
    safe_name = generate_safe_filename(original_name)
    file_path = get_upload_path(safe_name)
    file_type = get_file_type(original_name)

    # Stream file in 1 MB chunks to prevent OOM memory exhaustion vulnerabilities
    max_bytes = settings.max_upload_size_bytes
    size_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB chunking

    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(chunk_size):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    break
                await f.write(chunk)

        if size_bytes > max_bytes:
            if os.path.exists(file_path):
                os.remove(file_path)
            size_mb = size_bytes / (1024 * 1024)
            raise FileTooLargeError(size_mb, settings.max_upload_size_mb)

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e

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
