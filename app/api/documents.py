"""
Documents API - Upload and manage documents for bot training

Route convention: dynamic path values are always at the end of the URL.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status

from app.api.deps import CurrentUser, DBSession
from app.services.permissions import PermissionService
from app.enums import DocumentStatus
from app.schemas import (
    ApiResponse,
    DocumentUploadData,
    DocumentResponse,
    DocumentStatusData,
    DocumentListData,
)
from app.schemas.document import DocumentUploadRequest, DocumentUpdateBotsRequest
from app.services import DocumentService
from app.services import QueueService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=ApiResponse[DocumentUploadData],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(PermissionService.Documents.UPLOAD)],
)
async def upload_document(
    db: DBSession,
    current_user: CurrentUser,
    data_file: UploadFile = File(..., description="The document file to upload"),
    bot_ids: str = Form(..., description="JSON array of bot UUIDs (required, at least one)"),
):
    """
    Upload a document for processing.
    The document will be queued for async processing (parse -> chunk -> embed).
    Parser type is auto-detected from the file's MIME type.
    Use GET /documents/status/{id} to check processing status.
    """
    file_content = await data_file.read()

    upload_req = DocumentUploadRequest(
        file_name=data_file.filename or "",
        file_content_type=(data_file.content_type or "").strip().lower(),
        file_size=len(file_content),
        bot_ids=bot_ids,
    )

    service = DocumentService(db)
    document = await service.create_document(
        name=upload_req.file_name,
        file_content=file_content,
        mime_type=upload_req.file_content_type,
        organization_id=current_user.organization_id,
        bot_ids=upload_req.bot_ids,
    )

    await QueueService.enqueue_document_processing(document.id)

    return ApiResponse(
        success=True,
        message="Document accepted for processing",
        data=document,
    )


@router.get(
    "",
    response_model=ApiResponse[DocumentListData],
    dependencies=[Depends(PermissionService.Documents.READ)],
)
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


@router.get(
    "/status/{document_id}",
    response_model=ApiResponse[DocumentStatusData],
    dependencies=[Depends(PermissionService.Documents.READ)],
)
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


@router.get(
    "/detail/{document_id}",
    response_model=ApiResponse[DocumentResponse],
    dependencies=[Depends(PermissionService.Documents.READ)],
)
async def get_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get full document details."""
    service = DocumentService(db)
    document = await service.get_document(document_id, current_user.organization_id)
    return ApiResponse(success=True, data=document)


@router.patch(
    "/bots/{document_id}",
    response_model=ApiResponse[DocumentResponse],
    dependencies=[Depends(PermissionService.Documents.UPDATE)],
)
async def update_document_bots(
    data: DocumentUpdateBotsRequest,
    db: DBSession,
    current_user: CurrentUser,
    document_id: uuid.UUID = Path(..., description="The unique ID of the document")
):
    """Update bot associations for a document. REPLACES existing associations."""
    service = DocumentService(db)
    document = await service.update_document_bots(
        document_id, current_user.organization_id, data.bot_ids
    )
    return ApiResponse(
        success=True,
        message="Document bot associations updated successfully",
        data=document,
    )


@router.delete(
    "/{document_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(PermissionService.Documents.DELETE)],
)
async def delete_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a document and all its chunks."""
    service = DocumentService(db)
    await service.delete_document(document_id, current_user.organization_id)
    return ApiResponse(success=True, message="Document deleted successfully")
