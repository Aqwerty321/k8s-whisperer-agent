from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    port: int = 8000

    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_default_channel: str = "#alerts"
    public_base_url: str = "http://localhost:8000"
    slack_request_tolerance_seconds: int = 300

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    kubeconfig: str | None = None
    k8s_namespace: str = "default"
    observe_all_namespaces: bool = False
    observed_namespaces: list[str] = Field(default_factory=list)

    poll_interval_seconds: int = 30
    auto_approve_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    enable_background_polling: bool = False
    incident_dedup_window_seconds: int = 300
    checkpoint_store_path: str = "data/langgraph-checkpoints.pkl"
    verify_timeout_seconds: int = 20
    allow_workload_patches: bool = False
    enable_node_read_observation: bool = False

    prometheus_url: str | None = "http://localhost:9090"
    audit_log_path: str = "audit_log/audit.jsonl"

    stellar_network: str = "testnet"
    stellar_secret_key: str | None = None
    stellar_rpc_url: str | None = None
    stellar_contract_id: str | None = None

    @field_validator("public_base_url")
    @classmethod
    def strip_public_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("observed_namespaces", mode="before")
    @classmethod
    def normalize_observed_namespaces(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
