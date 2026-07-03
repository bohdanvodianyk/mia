"""Typed configuration for Mia, loaded from environment and `.env`.

Secrets are `SecretStr` so they never leak into logs or reprs. Nothing here is
required to *boot* (Gate G0); missing secrets are reported by `--check` and
enforced only by the phase that first needs them.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Owner lock
    owner_telegram_id: int | None = None

    # Provider secrets
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None

    # Google OAuth (Phase 4)
    google_oauth_client_secrets_file: Path = Path("./secrets/google_client_secret.json")
    google_token_file: Path = Path("./data/google_token.json")

    # Models — verify current ids against provider docs at each phase's build.
    claude_model_default: str = "claude-sonnet-4-6"
    claude_model_router: str = "claude-haiku-4-5-20251001"
    whisper_model: str = "whisper-1"

    # Runtime & guardrails
    mia_env: str = "dev"
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    default_timezone: str = "Europe/Madrid"
    daily_budget_usd: float = 1.0
    max_tool_iterations: int = 8

    # ── Derived paths ────────────────────────────────────────────
    @property
    def db_path(self) -> Path:
        return self.data_dir / "mia.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "mia.log"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def redacted_summary(self) -> dict[str, object]:
        """Config snapshot safe to log — secrets shown only as set/unset."""

        def mark(value: object) -> str:
            return "set" if value else "unset"

        return {
            "mia_env": self.mia_env,
            "log_level": self.log_level,
            "owner_telegram_id": mark(self.owner_telegram_id),
            "anthropic_api_key": mark(self.anthropic_api_key),
            "openai_api_key": mark(self.openai_api_key),
            "telegram_bot_token": mark(self.telegram_bot_token),
            "google_oauth_client_secrets_file": str(self.google_oauth_client_secrets_file),
            "google_token_file": str(self.google_token_file),
            "claude_model_default": self.claude_model_default,
            "claude_model_router": self.claude_model_router,
            "whisper_model": self.whisper_model,
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "log_file": str(self.log_file),
            "default_timezone": self.default_timezone,
            "daily_budget_usd": self.daily_budget_usd,
            "max_tool_iterations": self.max_tool_iterations,
        }


def load_settings() -> Settings:
    return Settings()
