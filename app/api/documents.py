"""
Documents API - Upload and manage documents for bot training
"""
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUser, DBSession
from app.enums import DocumentStatus
from app.schemas import (
    ApiResponse,
    DocumentUploadData,
    DocumentResponse,
    DocumentStatusData,
    DocumentListData,
)
from app.schemas.document import DocumentUploadRequest
from app.services import DocumentService
from app.services import QueueService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=ApiResponse[DocumentUploadData],
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    db: DBSession,
    current_user: CurrentUser,
    data_file: UploadFile = File(..., description="The document file to upload"),
    bot_ids: Optional[str] = Form(None, description="JSON array of bot UUIDs (optional)"),
    parser_type: str = Form(..., description="Parser type: 'simple' or 'docling'"),
):
    """
    Upload a document for processing.
    The document will be queued for async processing (parse -> chunk -> embed).
    Use GET /documents/{id}/status to check processing status.
    """
    file_content = await data_file.read()

    upload_req = DocumentUploadRequest(
        file_name=data_file.filename or "",
        file_content_type=(data_file.content_type or "").strip().lower(),
        file_size=len(file_content),
        bot_ids=bot_ids,
        parser_type=parser_type,
    )

    service = DocumentService(db)
    document = await service.create_document(
        name=upload_req.file_name,
        file_content=file_content,
        mime_type=upload_req.file_content_type,
        organization_id=current_user.organization_id,
        parser_type=upload_req.parser_type,
        bot_ids=upload_req.bot_ids,
    )

    await QueueService.enqueue_document_processing(document.id)

    return ApiResponse(
        success=True,
        message="Document accepted for processing",
        data=document,
    )


@router.get("", response_model=ApiResponse[DocumentListData])
async def list_documents(
    db: DBSession,
    current_user: CurrentUser,
    bot_id: Optional[uuid.UUID] = Query(None, description="Filter by bot ID"),
    doc_status: Optional[DocumentStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List documents. Optionally filter by bot_id and/or status."""
    service = DocumentService(db)
    result = await service.list_documents(
        current_user.organization_id, bot_id, doc_status, limit, offset
    )
    return ApiResponse(success=True, data=result)


@router.get("/{document_id}/status", response_model=ApiResponse[DocumentStatusData])
async def get_document_status(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Get the processing status of a document.

    Status values:
    - pending: Waiting to be processed
    - processing: Currently being parsed/chunked/embedded
    - ready: Successfully processed, ready for queries
    - failed: Processing failed, check error_message
    """
    service = DocumentService(db)
    document = await service.get_document(document_id, current_user.organization_id)
    return ApiResponse(success=True, data=document)


@router.get("/{document_id}/detail", response_model=ApiResponse[DocumentResponse])
async def get_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get full document details."""
    service = DocumentService(db)
    document = await service.get_document(document_id, current_user.organization_id)
    return ApiResponse(success=True, data=document)


@router.delete("/{document_id}", response_model=ApiResponse[None])
async def delete_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a document and all its chunks."""
    service = DocumentService(db)
    await service.delete_document(document_id, current_user.organization_id)
    return ApiResponse(success=True, message="Document deleted successfully")
