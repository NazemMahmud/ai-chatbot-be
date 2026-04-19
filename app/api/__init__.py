from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.bots import router as bots_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.widget import router as widget_router
# from app.api.integrations import router as integrations_router
from app.api.organization import router as organization_router
from app.api.members import router as members_router
from app.api.invitations import router as invitations_router
from app.api.roles import router as roles_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(organization_router)
api_router.include_router(bots_router)
api_router.include_router(chat_router)
api_router.include_router(documents_router)
api_router.include_router(widget_router)
# api_router.include_router(integrations_router)
api_router.include_router(members_router)
api_router.include_router(invitations_router)
api_router.include_router(roles_router)

__all__ = ["api_router"]
