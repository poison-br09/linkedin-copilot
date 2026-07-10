from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # App
    secret_key: str
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False

    # NVIDIA Nemotron
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"

    # Google Sheets (shared, one sheet for all users)
    google_sheet_id: str = ""
    google_service_account_path: str = "./service_account.json"

    # Scheduler
    watcher_interval_hours: int = 1
    processor_interval_minutes: int = 10
    processor_batch_size: int = 5
    max_retries: int = 3

    # Sessions (Playwright state files stored here)
    sessions_dir: str = "./sessions"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
