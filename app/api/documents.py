import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.document import (
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    URLIngestRequest,
)
from app.services.document import DocumentService

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png",
    "image/jpeg",
}


@router.post(
    "/bots/{bot_id}/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    bot_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    parser_type: str | None = Form(None),
):
    """Upload a file for processing. Returns 202 — processing happens asynchronously."""
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}",
        )

    service = DocumentService(db)
    doc = await service.upload_document(
        bot_id=bot_id,
        user_id=current_user.id,
        file=file,
        parser_type=parser_type,
    )
    return doc


@router.post(
    "/bots/{bot_id}/documents/url",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_url(
    bot_id: uuid.UUID,
    data: URLIngestRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Submit a URL for scraping and processing."""
    service = DocumentService(db)
    doc = await service.ingest_url(
        bot_id=bot_id,
        user_id=current_user.id,
        url=data.url,
        parser_type=data.parser_type,
    )
    return doc


@router.get("/bots/{bot_id}/documents", response_model=list[DocumentResponse])
async def list_documents(bot_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = DocumentService(db)
    return await service.list_documents(bot_id, current_user.id)


@router.get("/documents/{doc_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(doc_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = DocumentService(db)
    doc = await service.get_document_status(doc_id, current_user.id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: uuid.UUID, db: DBSession, current_user: CurrentUser):
    service = DocumentService(db)
    deleted = await service.delete_document(doc_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
