from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# The engine = the pool of connections to your database. Created ONCE for the app.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# A factory that produces short-lived "sessions" (one DB conversation each).
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# FastAPI dependency: hand a session to a request, then guarantee it's closed.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()