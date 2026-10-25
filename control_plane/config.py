from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    wake_data_dir: Path = Path("./data")
    wake_host: str = "0.0.0.0"
    wake_port: int = 8080
    wake_rate_limit_jobs_per_hour: int = 3
    wake_max_running_per_ip: int = 1
    wake_job_timeout_sec: int = 480
    wake_cmd_timeout_sec: int = 60

    wake_docker_host: str = "unix:///var/run/docker.sock"
    wake_sandbox_image: str = "wake-sandbox:local"
    wake_sandbox_runtime: str = "runsc"
    wake_sandbox_runtime_fallback: str = "runc"
    wake_sandbox_memory: str = "512m"
    wake_sandbox_cpus: float = 1.0
    wake_sandbox_pids: int = 128
    wake_sandbox_network_clone: str = "bridge"
    wake_output_max_bytes: int = 1_048_576

    wake_sandbox_remote_url: str = ""
    wake_sandbox_client_cert: str = ""
    wake_sandbox_client_key: str = ""
    wake_sandbox_ca_cert: str = ""

    # LLM — unused until build week
    vultr_inference_api_key: str = ""
    vultr_inference_base_url: str = ""
    vultr_inference_model: str = ""


settings = Settings()
