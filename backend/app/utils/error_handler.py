"""Centralised error handler utilities."""
from __future__ import annotations
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)


class FileTooLargeError(AppError):
    def __init__(self, size_mb: float, max_mb: int):
        super().__init__(
            f"File size {size_mb:.1f} MB exceeds maximum {max_mb} MB",
            status_code=413,
        )


class UnsupportedFileTypeError(AppError):
    def __init__(self, ext: str):
        super().__init__(
            f"File type '{ext}' is not supported. Allowed: .xlsx, .xls, .pdf, .png, .docx",
            status_code=415,
        )


class DocumentNotFoundError(AppError):
    def __init__(self, doc_id: str):
        super().__init__(f"Document '{doc_id}' not found", status_code=404)


class ExtractionError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"Content extraction failed: {reason}", status_code=422)


class AIEngineError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"AI extraction failed: {reason}", status_code=502)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "message": exc.message, "detail": exc.detail},
    )
