from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_provider: str = "openrouter"
    openai_model: str = "openrouter/free"
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    allowed_origins: str = "https://financial-dossier.vercel.app"
    phases_per_batch: int = 1
    analysis_results_dir: str = "output-content"
    workspace_retention_hours: float = 5.0
    runtime_mode: str = "production"
    resource_diagnostics_enabled: bool = True
    resource_diagnostics_interval_seconds: float = 2.0
    resource_diagnostics_dir: str = "resource-diagnostics"
    phase_agent_max_turns: int = 10
    max_repository_size_mb: int = 500

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def agent_model(self) -> str:
        return self.openai_model


settings = Settings()
