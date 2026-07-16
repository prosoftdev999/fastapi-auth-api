from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.users import router as users_router

app = FastAPI(
    title="FastAPI Authentication API",
    description="Authentication API with JWT, PostgreSQL, Docker, and tests.",
    version="0.2.0",
)

app.include_router(auth_router)
app.include_router(users_router)


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {
        "message": "FastAPI Authentication API is running",
        "status": "healthy",
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}