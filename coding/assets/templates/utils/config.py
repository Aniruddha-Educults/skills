from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

PREFIX: Final = "MYSVC_"  # TODO: set the service prefix and update .env.example.
ENV_DEFAULTS: Final[dict[str, str | None]] = {
    "ENVIRONMENT": "dev",
    "HOST": "127.0.0.1",
    "PORT": "9999",
    "LOG_LEVEL": "INFO",
    "CONFIG_YAML_PATH": "config.yaml",
    "MODELS_API_BASE_URL": "https://models.agents.seagate.com/v1",
    "MODELS_API_SECRET_NAME": "genai-models-api-key",
    "PROJECT_ORIGIN": None,
    "LLM_MODEL": None,
    "LLM_TIMEOUT_S": "60",
    "LLM_MAX_RETRIES": "3",
    "LLM_REASONING_EFFORT": "",
    "LLM_USE_RESPONSES_API": "false",
    "LANGFUSE_ENABLED": "false",
    "LANGFUSE_TRACING_ENABLED": "false",
    "LANGFUSE_BASE_URL": "",
    "LANGFUSE_PUBLIC_KEY_SECRET_NAME": "langfuse-public-key",
    "LANGFUSE_SECRET_KEY_SECRET_NAME": "langfuse-secret-key",
    "LANGFUSE_PROMPT_LABEL": "production",
    "LANGFUSE_TIMEOUT_S": "10",
    "LANGFUSE_PROMPT_CACHE_TTL_S": "300",
    "PROMPTS_PATH": str(Path(__file__).resolve().parents[1] / "llm" / "prompts.yaml"),
    "SECTION_PROMPT_PATH": str(Path(__file__).resolve().parents[1] / "llm" / "section_prompts.yaml"),
    "SECTION_PROMPT_NAME": "sectioned-report",
}


class ConfigError(ValueError):
    pass


def _get(name: str) -> str:
    value = os.environ.get(PREFIX + name, ENV_DEFAULTS[name])
    if value is None or (not value.strip() and name not in {"LANGFUSE_BASE_URL", "LLM_REASONING_EFFORT"}):
        raise ConfigError(f"Required environment variable '{PREFIX + name}' must not be empty")
    return value.strip()


def _number(name: str, *, integer: bool = False, minimum: float = 0) -> float:
    try:
        value = float(int(_get(name))) if integer else float(_get(name))
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"Environment variable '{PREFIX + name}' must be numeric") from None
    if not math.isfinite(value) or value < minimum:
        raise ConfigError(f"Environment variable '{PREFIX + name}' must be finite and >= {minimum}")
    return value


def _bool(name: str) -> bool:
    value = _get(name).lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise ConfigError(f"Environment variable '{PREFIX + name}' must be a boolean")
    return value in {"true", "1", "yes", "on"}


def _url(name: str) -> str:
    value = _get(name).rstrip("/")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username
        valid = valid and not parsed.password and not parsed.query and not parsed.fragment
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ConfigError(f"Environment variable '{PREFIX + name}' must be an HTTP(S) URL without credentials")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    host: str
    port: int
    log_level: str
    config_yaml_path: Path
    models_api_base_url: str
    models_api_secret_name: str
    project_origin: str
    llm_model: str
    llm_timeout_s: float
    llm_max_retries: int
    llm_reasoning_effort: str | None
    llm_use_responses_api: bool
    langfuse_enabled: bool
    langfuse_tracing_enabled: bool
    langfuse_base_url: str
    langfuse_public_key_secret_name: str
    langfuse_secret_key_secret_name: str
    langfuse_prompt_label: str
    langfuse_timeout_s: float
    langfuse_prompt_cache_ttl_s: int
    prompts_path: Path
    section_prompt_path: Path
    section_prompt_name: str


def load_settings() -> Settings:
    port = int(_number("PORT", integer=True, minimum=1))
    if port > 65535:
        raise ConfigError(f"Environment variable '{PREFIX}PORT' must be <= 65535")
    level = _get("LOG_LEVEL").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"Environment variable '{PREFIX}LOG_LEVEL' is not a supported log level")
    langfuse_enabled = _bool("LANGFUSE_ENABLED")
    tracing_enabled = _bool("LANGFUSE_TRACING_ENABLED")
    langfuse_base_url = (
        _url("LANGFUSE_BASE_URL") if langfuse_enabled or tracing_enabled or _get("LANGFUSE_BASE_URL") else ""
    )
    return Settings(
        environment=_get("ENVIRONMENT"),
        host=_get("HOST"),
        port=port,
        log_level=level,
        config_yaml_path=Path(_get("CONFIG_YAML_PATH")).expanduser(),
        models_api_base_url=_url("MODELS_API_BASE_URL"),
        models_api_secret_name=_get("MODELS_API_SECRET_NAME"),
        project_origin=_get("PROJECT_ORIGIN"),
        llm_model=_get("LLM_MODEL"),
        llm_timeout_s=_number("LLM_TIMEOUT_S", minimum=0.001),
        llm_max_retries=int(_number("LLM_MAX_RETRIES", integer=True)),
        llm_reasoning_effort=_get("LLM_REASONING_EFFORT") or None,
        llm_use_responses_api=_bool("LLM_USE_RESPONSES_API"),
        langfuse_enabled=langfuse_enabled,
        langfuse_tracing_enabled=tracing_enabled,
        langfuse_base_url=langfuse_base_url,
        langfuse_public_key_secret_name=_get("LANGFUSE_PUBLIC_KEY_SECRET_NAME"),
        langfuse_secret_key_secret_name=_get("LANGFUSE_SECRET_KEY_SECRET_NAME"),
        langfuse_prompt_label=_get("LANGFUSE_PROMPT_LABEL"),
        langfuse_timeout_s=_number("LANGFUSE_TIMEOUT_S", minimum=0.001),
        langfuse_prompt_cache_ttl_s=int(_number("LANGFUSE_PROMPT_CACHE_TTL_S", integer=True)),
        prompts_path=Path(_get("PROMPTS_PATH")).expanduser(),
        section_prompt_path=Path(_get("SECTION_PROMPT_PATH")).expanduser(),
        section_prompt_name=_get("SECTION_PROMPT_NAME"),
    )


@cache
def get_settings() -> Settings:
    """Call once at startup; inject the same immutable snapshot throughout the service."""
    return load_settings()
