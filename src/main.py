from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine
from app.domain import model
from app.domain.auth import router as auth_router
from app.domain.project import router as project_router
from app.domain.storage import router as storage_router
from app.domain.memories import router as memories_router
from app.domain.payments import router as payments_router
from app.services.speech_to_text import router as speech_router


Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Memoir API",
    description="Backend API for Memoir onboarding, file storage, memories (photo/voice), and checkout payments",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(project_router)
app.include_router(storage_router)
app.include_router(memories_router)
app.include_router(payments_router)
app.include_router(speech_router)


@app.get("/")
def root():
    return {
        "message": "Memoir API is running",
        "status": "healthy",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "message": "Service is operational",
    }