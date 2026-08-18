import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.core.config import get_settings
from app.db.database import Base, engine, sync_database_schema
from app.models.user import User  # noqa: F401 — registers model with SQLAlchemy metadata

settings = get_settings()

Base.metadata.create_all(bind=engine)
sync_database_schema(engine)


app = FastAPI(
    title="Memory App API"
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware is required by Google OAuth to store the 'state' CSRF token
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)

app.include_router(auth_router)

# Mount static files if directory exists
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "API is running"}


@app.get("/health")
def health():
    return {"status": "ok", "message": "API is running"}

