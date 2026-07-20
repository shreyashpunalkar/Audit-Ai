"""Pydantic schemas for request/response validation."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional, List, Dict
from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    message: str


class DocumentStatusResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    extracted_json: Optional[Dict[str, Any]] = None
    validation_errors: Optional[List[str]] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProcessRequest(BaseModel):
    document_id: str


class JsonUpdateRequest(BaseModel):
    json_data: Dict[str, Any]


class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
