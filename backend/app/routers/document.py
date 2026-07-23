"""Document router — GET/DELETE /api/document/{id}, PUT /api/document/{id}/json"""
import logging
import os
import json
from urllib.parse import quote
from fastapi import APIRouter, Depends
from fastapi.responses import Response, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentDetailResponse, JsonUpdateRequest
from app.services.validator import validate_checksheet_json, serialize_json
from app.utils.error_handler import DocumentNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["document"])


def _ensure_dict(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return val


@router.get("/document/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full document details including extracted JSON and validation status."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise DocumentNotFoundError(document_id)

    return DocumentDetailResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        extracted_json=_ensure_dict(doc.extracted_json),
        validation_errors=doc.validation_errors,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.put("/document/{document_id}/json", response_model=DocumentDetailResponse)
async def update_document_json(
    document_id: str,
    body: JsonUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update (save edited) JSON for a document, re-validates before saving."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise DocumentNotFoundError(document_id)

    try:
        corrected, errors = validate_checksheet_json(body.json_data)
    except ValueError as e:
        corrected = body.json_data
        errors = [str(e)]

    doc.extracted_json = corrected
    doc.validation_errors = errors
    await db.commit()
    await db.refresh(doc)

    return DocumentDetailResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        extracted_json=_ensure_dict(doc.extracted_json),
        validation_errors=doc.validation_errors,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/download/{document_id}")
async def download_json(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download the extracted JSON as a .json file."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise DocumentNotFoundError(document_id)

    if not doc.extracted_json:
        return JSONResponse(
            status_code=422,
            content={"error": True, "message": "No JSON available. Process the document first."},
        )

    json_data = _ensure_dict(doc.extracted_json) or doc.extracted_json
    json_str = serialize_json(json_data) if isinstance(json_data, dict) else json.dumps(json_data, indent=2)
    base_name = os.path.splitext(doc.original_filename)[0]
    # Sanitize base_name to ensure standard ASCII compatibility for filename="..."
    safe_base = "".join(c if c.isalnum() or c in "._-" else "_" for c in base_name)
    download_name = f"{safe_base}_extracted.json"

    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"; filename*=utf-8\'\'{quote(download_name)}'
    }
    return Response(
        content=json_str,
        media_type="application/json",
        headers=headers,
    )


@router.delete("/document/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document record and its uploaded file."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise DocumentNotFoundError(document_id)

    # Remove file from disk safely if present
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError as e:
            logger.warning(f"Could not remove file {doc.file_path}: {e}")

    await db.delete(doc)
    await db.commit()
