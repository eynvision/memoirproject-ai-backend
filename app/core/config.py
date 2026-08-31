from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_jwks_url: str
    supabase_jwt_aud: str = "authenticated"
    database_url: str 
    cors_origins: str 

      # ← add this


    model_config = SettingsConfigDict(env_file=".env", case_insensitive=True)


settings = Settings()

