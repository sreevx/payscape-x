"""Application configuration.

All configuration is driven by environment variables (see .env.example).
Secrets such as database credentials are never hardcoded here — the default
DATABASE_URL below is a local development default only and must be overridden
in any real environment.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "PAYSCAPE-X"
    service_name: str = "payscape-x"
    app_env: str = "development"  # development | staging | production
    app_version: str = "0.1.0"
    debug: bool = False

    # --- Logging ---------------------------------------------------------
    log_level: str = "INFO"

    # --- Demo Mode -------------------------------------------------------
    # When enabled the backend may serve synthetic demo data. No AI output
    # is generated in Part 1 regardless of this flag.
    demo_mode: bool = True

    # --- Database --------------------------------------------------------
    # PostgreSQL via psycopg 3. Local development default only — always
    # override with DATABASE_URL in real environments.
    database_url: str = (
        "postgresql+psycopg://payscape:payscape@localhost:5432/payscape_x"
    )

    # --- CORS ------------------------------------------------------------
    # Comma-separated list of allowed origins (frontend base URLs).
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    # --- Decision Agent (Part 8) ----------------------------------------
    # LLM provider configuration. The default "none" makes the Decision
    # Agent use the mandatory deterministic fallback — no API key needed.
    # Set DECISION_LLM_PROVIDER=openai_compatible to enable the
    # OpenAI-compatible HTTP provider (see .env.example). Secrets such as
    # the API key are never hardcoded here.
    decision_llm_provider: str = "none"   # none | openai_compatible
    decision_llm_base_url: str = ""
    decision_llm_api_key: str = ""
    decision_llm_model: str = ""
    decision_llm_timeout_ms: int = 30000

    # --- Razorpay webhooks (Part 9) -------------------------------------
    # TEST-MODE webhook secret. When set, every /api/v1/webhooks/razorpay
    # request MUST carry a valid X-Razorpay-Signature (HMAC-SHA256 of the
    # raw body); invalid or missing signatures are rejected with 400. When
    # empty, signature verification cannot run: the endpoint only accepts
    # explicit demo-mode deliveries (X-PAYSCAPE-DEMO: 1, demo_mode enabled)
    # and records signature_verified=false. Secrets are never hardcoded.
    razorpay_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()