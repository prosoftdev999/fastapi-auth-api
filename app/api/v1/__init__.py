from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.oauth import router as oauth_router
from app.api.users import router as users_router
from app.api.websocket import router as websocket_router

# v1 is the current, canonical API surface — every router unchanged from
# how it's always behaved. Mounted at /api/v1 in app/main.py.
router = APIRouter()
router.include_router(auth_router)
router.include_router(oauth_router)
router.include_router(users_router)
router.include_router(admin_router)
router.include_router(files_router)
router.include_router(websocket_router)
