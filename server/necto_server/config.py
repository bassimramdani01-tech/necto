from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NECTO_",
        # Works whether the process starts in server/ or the repo root.
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://necto:necto@127.0.0.1:5432/necto"
    log_level: str = "info"
    schema_version: int = 1
    # When set, every /v1 endpoint (including the WebSocket) requires X-API-Key.
    api_key: str | None = None
    # When true (NECTO_SEED=1), fill an empty database with demo runs on first boot.
    seed: bool = False
    # When set (NECTO_WEB_DIR), serve this built web UI from the API at "/".
    web_dir: str | None = None


settings = Settings()
