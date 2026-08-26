import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.example import router as example_router
from src.api.memoir import router as memoir_router
from src.api.memory import router as memory_router
from src.api.user import router as user_router
from src.core.app_lifespan import lifespan
from src.core.logging_config import setup_logging

setup_logging()

app = FastAPI(title="Memoir Backend", lifespan=lifespan)


def get_frontend_origins() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGINS", "")

    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_frontend_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(example_router)
app.include_router(memoir_router)
app.include_router(memory_router)
app.include_router(user_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
