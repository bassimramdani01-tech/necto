from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NECTO_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://necto:necto@127.0.0.1:5432/necto"
    log_level: str = "info"
    schema_version: int = 1


settings = Settings()
