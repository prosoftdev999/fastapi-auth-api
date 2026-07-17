from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.oauth import router as oauth_router
from app.api.v2.users import router as users_v2_router
from app.api.websocket import router as websocket_router

# v2 only evolves what actually changed (GET/PATCH /users/me — see
# app/api/v2/users.py) — everything else is identical to v1 and reuses the
# exact same routers. Mounted at /api/v2 in app/main.py.
router = APIRouter()
router.include_router(auth_router)
router.include_router(oauth_router)
router.include_router(users_v2_router)
router.include_router(admin_router)
router.include_router(files_router)
router.include_router(websocket_router)
