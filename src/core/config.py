import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Memoir Backend API"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    API_V1_STR: str = ""
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./memoir.db")
    DIRECT_URL: str = os.getenv("DIRECT_URL", "sqlite:///./memoir.db")

    # JWT / Security (default >= 32 chars)
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "memoir-super-secure-jwt-secret-key-at-least-32-chars")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # File Storage (default >= 32 chars signing secret)
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # "local" or "s3"
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "uploads")
    STORAGE_SIGNING_SECRET: str = os.getenv("STORAGE_SIGNING_SECRET", "memoir-storage-signing-secret-key-32-bytes-long")
    STORAGE_URL_EXPIRE_SECONDS: int = int(os.getenv("STORAGE_URL_EXPIRE_SECONDS", "3600"))

    # AWS S3 (Optional if STORAGE_BACKEND == "s3")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "")

    # Speech-to-Text (Whisper / AssemblyAI)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ASSEMBLYAI_API_KEY: str = os.getenv("ASSEMBLYAI_API_KEY", "")

    # Stripe Payments
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mock_memoir_publishable_key")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    FLAT_RATE_PRICE_USD: float = float(os.getenv("FLAT_RATE_PRICE_USD", "299.00"))

    model_config = ConfigDict(case_sensitive=True, extra="allow")


settings = Settings()
