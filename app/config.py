from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VIDMAX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "VidMax"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./vidmax.db"
    storage_dir: Path = Path("./storage")

    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_output_bytes: int = Field(default=500 * 1024 * 1024, gt=0)
    processing_timeout_seconds: int = Field(default=120, gt=0)
    job_ttl_hours: int = Field(default=24, gt=0)
    media_min_bytes: int = Field(default=1024, gt=0)
    ffprobe_timeout_seconds: int = Field(default=30, gt=0)
    duration_tolerance_seconds: float = Field(default=2.0, ge=0)
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None

    enable_local_uploads: bool = False
    enable_youtube_pytubefix_download: bool = False
    youtube_download_timeout_seconds: int = Field(default=60, gt=0)
    youtube_download_max_retries: int = Field(default=2, ge=0, le=5)
    enable_metadata_inspection: bool = True
    enable_facebook_metadata: bool = False
    facebook_access_token: SecretStr | None = None

    youtube_oembed_url: str = "https://www.youtube.com/oembed"
    facebook_oembed_url: str = "https://graph.facebook.com/v19.0/oembed_video"
    http_timeout_seconds: float = Field(default=5.0, gt=0)
    metadata_max_bytes: int = Field(default=64 * 1024, gt=0)
    error_message_max_chars: int = Field(default=500, gt=0)

    @field_validator("storage_dir", mode="before")
    @classmethod
    def coerce_storage_dir(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value)
        return value


@lru_cache
def load_settings() -> Settings:
    return Settings()
