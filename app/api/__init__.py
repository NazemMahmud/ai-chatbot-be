from fastapi import APIRouter

from app.api.bots import router as bots_router
from app.api.documents import router as documents_router

api_router = APIRouter(prefix="/api")
api_router.include_router(bots_router)
api_router.include_router(documents_router)

__all__ = ["api_router"]
