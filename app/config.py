import base64
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str

    # Face pipeline
    matching_enabled: bool = False
    face_provider: str = "app.opencv_provider:create_provider"
    face_model_path: str | None = "/app/models"
    face_model_version: str = "yunet-2023mar+sface-2021dec"
    face_embedding_dim: int = 128
    face_detection_score_threshold: float = 0.85
    face_detection_nms_threshold: float = 0.3
    face_min_size: int = 40
    image_max_side: int = 1600
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 40_000_000

    # Authentication and HTTP security
    allowed_hosts: str = "localhost,127.0.0.1,testserver,.onrender.com"
    session_cookie_secure: bool = True
    session_hours: int = 8
    invite_hours: int = 24
    inference_retention_days: int = 30
    inference_daily_limit: int = 100
    bootstrap_secret: str | None = None
    initial_admin_email: str | None = None
    initial_admin_password: str | None = None

    # Explicitly consented biometric retention. The key must be a Fernet key.
    consented_storage_enabled: bool = False
    data_encryption_key: str | None = None
    data_encryption_key_version: str = "v1"
    retained_upload_days: int = 30
    retained_image_max_side: int = 1024
    consent_text_version: str = "2026-11-05"

    # Optional match narration. Only candidate names and scores are sent.
    match_narration_enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-luna"
    openai_timeout_seconds: float = 12.0

    # Operations
    deployment_environment: str = "development"
    experiment_variant: str = "control"
    log_level: str = "INFO"
    self_similarity_threshold: float = 0.55

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg3(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("deployment_environment", "experiment_variant", "log_level")
    @classmethod
    def validate_runtime_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 64 or not normalized.replace("-", "").replace("_", "").isalnum():
            raise ValueError("runtime labels must contain only letters, numbers, hyphens, or underscores")
        return normalized

    @field_validator("self_similarity_threshold")
    @classmethod
    def validate_similarity_threshold(cls, value: float) -> float:
        if not -1.0 <= value <= 1.0:
            raise ValueError("self similarity threshold must be between -1 and 1")
        return value

    @field_validator("face_detection_score_threshold", "face_detection_nms_threshold")
    @classmethod
    def validate_probability(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("face detector thresholds must be between 0 and 1")
        return value

    @field_validator("retained_upload_days")
    @classmethod
    def validate_retention(cls, value: int) -> int:
        if not 1 <= value <= 365:
            raise ValueError("retained upload days must be between 1 and 365")
        return value

    @field_validator("data_encryption_key")
    @classmethod
    def validate_encryption_key(cls, value: str | None) -> str | None:
        if value:
            try:
                decoded = base64.urlsafe_b64decode(value.encode("ascii"))
            except (ValueError, UnicodeEncodeError) as exc:
                raise ValueError("data encryption key must be a Fernet key") from exc
            if len(decoded) != 32:
                raise ValueError("data encryption key must decode to 32 bytes")
        return value

    @field_validator("openai_timeout_seconds")
    @classmethod
    def validate_openai_timeout(cls, value: float) -> float:
        if not 1 <= value <= 60:
            raise ValueError("OpenAI timeout must be between 1 and 60 seconds")
        return value

    @property
    def retention_available(self) -> bool:
        return self.consented_storage_enabled and bool(self.data_encryption_key)

    @property
    def narration_available(self) -> bool:
        return self.match_narration_enabled and bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
