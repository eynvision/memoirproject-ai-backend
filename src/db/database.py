import os

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine, inspect, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")


def _get_working_engine(url: str):
    """
    Creates a SQLAlchemy engine. If a remote Postgres URL cannot connect
    due to network/DNS issues, it automatically falls back to local SQLite so
    the app remains functional.
    """
    try:
        eng = create_engine(
            url,
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
            pool_pre_ping=True,
        )
        if not url.startswith("sqlite"):
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
        return eng
    except Exception as exc:
        print(f"⚠️ Postgres connection failed ({exc}). Falling back to local SQLite database.")
        fallback_url = "sqlite:///./app.db"
        return create_engine(fallback_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)


engine = _get_working_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()



def sync_database_schema(db_engine):
    """
    Safely inspects existing database tables and adds any missing columns.
    Ensures pre-existing tables in Postgres/SQLite match the SQLAlchemy models.
    """
    try:
        inspector = inspect(db_engine)
        if "users" not in inspector.get_table_names():
            return

        existing_columns = {col["name"] for col in inspector.get_columns("users")}

        with db_engine.connect() as conn:
            if "name" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN name VARCHAR;"))
            if "password_hash" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR;"))
            if "provider" not in existing_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN provider VARCHAR DEFAULT 'email';"))
            conn.commit()

    except Exception as exc:
        print(f"[Warning] DB schema sync info: {exc}")


