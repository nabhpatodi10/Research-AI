from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_csv(name: str) -> tuple[str, ...]:
    raw = _env_str(name)
    if not raw:
        return ()
    values = [item.strip() for item in raw.split(",")]
    return tuple(item for item in values if item)


def _samesite(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"lax", "strict", "none"}:
        return normalized
    return "lax"


@dataclass(frozen=True)
class Settings:
    log_level: str
    noisy_lib_log_level: str
    noisy_library_loggers: tuple[str, ...]

    frontend_base_url: str
    cors_origins: tuple[str, ...]

    session_secret: str
    session_ttl_seconds: int
    cookie_name: str
    cookie_secure: bool
    cookie_domain: str | None
    cookie_samesite: str

    firebase_web_api_key: str | None
    google_oauth_client_id: str | None
    google_oauth_client_secret: str | None
    google_oauth_redirect_uri: str | None
    firebase_auth_timeout_seconds: float

    gemini_api_key: str | None
    search_engine_id: str | None
    custom_search_timeout_seconds: float
    custom_search_base_url: str

    google_project_id: str | None
    google_cloud_project: str | None
    google_cloud_location: str | None
    google_application_credentials: str | None
    vector_split_chunk_size: int
    vector_split_chunk_overlap: int

    scrape_timeout_ms: int
    web_search_total_timeout_seconds: float
    web_search_scrape_timeout_seconds: float
    min_web_documents_low: int
    min_web_documents_medium: int
    min_web_documents_high: int

    research_background_poll_interval_seconds: float
    research_background_batch_size: int
    research_background_max_retries: int

    pdf_probe_timeout_seconds: float
    pdf_primary_timeout_seconds: float
    pdf_in_memory_timeout_seconds: float
    pdf_min_partial_chars: int
    pdf_background_poll_interval_seconds: float
    pdf_background_max_retries: int
    pdf_background_batch_size: int
    pdf_http_timeout_seconds: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    frontend_base_url = _env_str("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    return Settings(
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        noisy_lib_log_level=_env_str("NOISY_LIB_LOG_LEVEL", "WARNING").upper(),
        noisy_library_loggers=(
            "httpx",
            "httpcore",
            "uvicorn.access",
            "google.auth",
            "google.api_core",
            "google.cloud",
            "google_genai",
        ),
        frontend_base_url=frontend_base_url,
        cors_origins=_env_csv("CORS_ORIGINS"),
        session_secret=_env_str("APP_SESSION_SECRET"),
        session_ttl_seconds=_env_int("APP_SESSION_TTL_SECONDS", 604800),
        cookie_name=_env_str("COOKIE_NAME", "ra_session"),
        cookie_secure=_env_bool("COOKIE_SECURE", True),
        cookie_domain=(_env_str("COOKIE_DOMAIN") or None),
        cookie_samesite=_samesite(_env_str("COOKIE_SAMESITE", "lax")),
        firebase_web_api_key=(_env_str("FIREBASE_WEB_API_KEY") or None),
        google_oauth_client_id=(_env_str("GOOGLE_OAUTH_CLIENT_ID") or None),
        google_oauth_client_secret=(_env_str("GOOGLE_OAUTH_CLIENT_SECRET") or None),
        google_oauth_redirect_uri=(_env_str("GOOGLE_OAUTH_REDIRECT_URI") or None),
        firebase_auth_timeout_seconds=_env_float("FIREBASE_AUTH_TIMEOUT_SECONDS", 20.0),
        gemini_api_key=(_env_str("GEMINI_API_KEY") or None),
        search_engine_id=(_env_str("SEARCH_ENGINE_ID") or None),
        custom_search_timeout_seconds=_env_float("CUSTOM_SEARCH_TIMEOUT_SECONDS", 20.0),
        custom_search_base_url=_env_str(
            "CUSTOM_SEARCH_BASE_URL", "https://www.googleapis.com/customsearch/v1"
        ),
        google_project_id=(_env_str("GOOGLE_PROJECT_ID") or None),
        google_cloud_project=(_env_str("GOOGLE_CLOUD_PROJECT") or None),
        google_cloud_location=(_env_str("GOOGLE_CLOUD_LOCATION") or None),
        google_application_credentials=(_env_str("GOOGLE_APPLICATION_CREDENTIALS") or None),
        vector_split_chunk_size=_env_int("VECTOR_SPLIT_CHUNK_SIZE", 6500),
        vector_split_chunk_overlap=_env_int("VECTOR_SPLIT_CHUNK_OVERLAP", 200),
        scrape_timeout_ms=_env_int("SCRAPE_TIMEOUT_MS", 20_000),
        web_search_total_timeout_seconds=_env_float("WEB_SEARCH_TOTAL_TIMEOUT_SECONDS", 40.0),
        web_search_scrape_timeout_seconds=_env_float("WEB_SEARCH_SCRAPE_TIMEOUT_SECONDS", 30.0),
        min_web_documents_low=_env_int("MIN_WEB_DOCUMENTS_LOW", 1),
        min_web_documents_medium=_env_int("MIN_WEB_DOCUMENTS_MEDIUM", 2),
        min_web_documents_high=_env_int("MIN_WEB_DOCUMENTS_HIGH", 4),
        research_background_poll_interval_seconds=_env_float(
            "RESEARCH_BACKGROUND_POLL_INTERVAL_SECONDS", 1.0
        ),
        research_background_batch_size=_env_int("RESEARCH_BACKGROUND_BATCH_SIZE", 8),
        research_background_max_retries=_env_int("RESEARCH_BACKGROUND_MAX_RETRIES", 2),
        pdf_probe_timeout_seconds=_env_float("PDF_PROBE_TIMEOUT_SECONDS", 2.5),
        pdf_primary_timeout_seconds=_env_float("PDF_PRIMARY_TIMEOUT_SECONDS", 30.0),
        pdf_in_memory_timeout_seconds=_env_float("PDF_IN_MEMORY_TIMEOUT_SECONDS", 180.0),
        pdf_min_partial_chars=_env_int("PDF_MIN_PARTIAL_CHARS", 500),
        pdf_background_poll_interval_seconds=_env_float(
            "PDF_BACKGROUND_POLL_INTERVAL_SECONDS", 2.0
        ),
        pdf_background_max_retries=_env_int("PDF_BACKGROUND_MAX_RETRIES", 3),
        pdf_background_batch_size=_env_int("PDF_BACKGROUND_BATCH_SIZE", 2),
        pdf_http_timeout_seconds=_env_float("PDF_HTTP_TIMEOUT_SECONDS", 20.0),
    )


def validate_security_settings(settings: Settings) -> None:
    if len(settings.session_secret) < 32:
        raise RuntimeError("APP_SESSION_SECRET must be set and at least 32 characters.")
    if settings.session_ttl_seconds < 300 or settings.session_ttl_seconds > 2_592_000:
        raise RuntimeError("APP_SESSION_TTL_SECONDS must be between 300 and 2592000 seconds.")
