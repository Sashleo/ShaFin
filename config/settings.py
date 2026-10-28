"""
config/settings.py — Application settings loaded from environment variables.
All configuration lives here. No hardcoded values anywhere else.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache

# Placeholder values shipped in .env.example — must never be accepted at runtime.
_PLACEHOLDER_SECRETS = {
    "", "generate-a-64-char-random-string-here", "set-a-strong-password-here",
    "change-me", "changeme",
}


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_VERSION: str = "0.1.0"
    APP_SECRET_KEY: str
    DEBUG: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_PATH: str = "/app/data/shafin.db"
    REPORTS_DIR: str = "/app/data/reports"
    DB_MASTER_PASSWORD: str

    # ── Security ──────────────────────────────────────────────────────────────
    SESSION_EXPIRE_HOURS: int = 2
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15
    # First-run admin creation is gated: either the request originates from
    # localhost, OR this token is set and supplied on the creation request.
    ADMIN_BOOTSTRAP_TOKEN: str = ""

    # ── Backup ────────────────────────────────────────────────────────────────────
    BACKUP_COPY_DIR: str = ""

    # ── Demo mode: fictional companies, a demo login and a banner ─────────────────
    DEMO_MODE: bool = False

    # ── Startup secret validation — refuse to boot on blank/default/short secrets ──
    @field_validator("APP_SECRET_KEY")
    @classmethod
    def _check_app_secret(cls, v: str) -> str:
        if v in _PLACEHOLDER_SECRETS or len(v) < 32:
            raise ValueError(
                "APP_SECRET_KEY must be set to a strong value of at least 32 characters "
                "(not the .env.example placeholder). Generate one with: "
                "python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @field_validator("DB_MASTER_PASSWORD")
    @classmethod
    def _check_db_password(cls, v: str) -> str:
        if v in _PLACEHOLDER_SECRETS or len(v) < 12:
            raise ValueError(
                "DB_MASTER_PASSWORD must be set to a strong value of at least 12 "
                "characters (not the .env.example placeholder)."
            )
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
