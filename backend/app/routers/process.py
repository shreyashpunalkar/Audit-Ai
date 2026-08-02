"""Process router — POST /api/process/{id}"""
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, AsyncSessionLocal
from app.models.document import Document
from app.schemas.document import DocumentStatusResponse
from app.services.extractor import extract_content
from app.services.ai_engine import run_ai_extraction
from app.services.validator import validate_checksheet_json
from app.utils.error_handler import DocumentNotFoundError, ExtractionError, AIEngineError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["process"])


async def _run_pipeline(doc_id: str):
    """Full processing pipeline as a background task."""
    from datetime import datetime, timezone
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error(f"Pipeline: document {doc_id} not found")
            return

        try:
            # Stage 1: Extracting
            doc.status = "extracting"
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()

            raw_content = extract_content(doc.file_path, doc.file_type)
            doc.raw_content = raw_content[:100_000]  # cap storage

            # Stage 2: AI Analysis
            doc.status = "ai_analysis"
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()

            extracted = await run_ai_extraction(raw_content, doc.file_path)

            # Stage 3: Validating
            doc.status = "validating"
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()

            corrected, errors = validate_checksheet_json(extracted)
            doc.extracted_json = corrected
            doc.validation_errors = errors if errors else []

            # Stage 4: Complete
            doc.status = "completed"
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(f"Pipeline complete for document {doc_id}")

        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)
            doc.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error(f"Pipeline error for {doc_id}: {e}")


@router.post("/process/{document_id}", response_model=DocumentStatusResponse)
async def process_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger the AI extraction pipeline for an uploaded document.
    Processing runs in the background; poll GET /api/document/{id} for status.
    Auto-reschedules stuck processes (>25s inactivity).
    """
    from datetime import datetime, timezone
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise DocumentNotFoundError(document_id)

    # Check if stuck in intermediate status (>25s)
    now = datetime.now(timezone.utc)
    is_stuck = False
    if doc.updated_at:
        delta = (now - doc.updated_at).total_seconds()
        if delta > 25:
            is_stuck = True

    if doc.status in ("ai_analysis", "extracting", "validating") and not is_stuck:
        return DocumentStatusResponse(
            id=doc.id,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    # Reset for processing / reprocessing if stuck or requested
    logger.info(f"Scheduling pipeline execution for document {document_id} (is_stuck={is_stuck})")
    doc.status = "uploaded"
    doc.error_message = None
    doc.extracted_json = None
    doc.validation_errors = None
    doc.updated_at = now
    await db.commit()

    background_tasks.add_task(_run_pipeline, document_id)

    return DocumentStatusResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status="processing",
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
