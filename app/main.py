from fastapi import FastAPI

app = FastAPI(
    title="FastAPI Authentication API",
    description="Authentication API with JWT, PostgreSQL, Docker, and tests.",
    version="0.1.0",
)


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {
        "message": "FastAPI Authentication API is running",
        "status": "healthy",
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}