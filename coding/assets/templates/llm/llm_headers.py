from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

import yaml
from src.utils.config import Settings

from src.utils.logger import CustomLogger

logger = CustomLogger(__name__)

_request_headers: ContextVar[Mapping[str, str] | None] = ContextVar("llm_request_headers", default=None)


@contextmanager
def request_headers_scope(headers: Mapping[str, str]) -> Iterator[None]:
    token = _request_headers.set(dict(headers))
    try:
        yield
    finally:
        _request_headers.reset(token)


def current_request_headers() -> Mapping[str, str] | None:
    headers = _request_headers.get()
    return dict(headers) if headers is not None else None


def _header(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or "\r" in value or "\n" in value:
        logger.error(f"Missing or invalid LLM header '{name}'")
        raise ValueError(f"Missing or invalid LLM header '{name}'")
    return value.strip()


def default_llm_headers(settings: Settings, *, user_email: str) -> dict[str, str]:
    try:
        config = yaml.safe_load(settings.config_yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        logger.error("Cannot read EAP metadata for LLM headers")
        raise ValueError("Cannot read EAP metadata for LLM headers") from None
    if not isinstance(config, dict) or not isinstance(config.get("metadata"), dict):
        logger.error("EAP config must contain metadata.urlName")
        raise ValueError("EAP config must contain metadata.urlName")
    if "urlName" not in config["metadata"]:
        logger.error("EAP config must contain metadata.urlName")
        raise ValueError("EAP config must contain metadata.urlName")
    project_url = config['metadata']['urlName']  # fmt: skip
    return {
        "x-project-url": _header("x-project-url", project_url),
        "x-project-origin": _header("x-project-origin", settings.project_origin),
        "x-user-email": _header("x-user-email", user_email),
    }


def resolve_llm_headers(
    settings: Settings,
    request_headers: Mapping[str, str] | None = None,
    *,
    project_origin: str | None = None,
    user_email: str | None = None,
) -> dict[str, str]:
    incoming = current_request_headers() if request_headers is None else request_headers
    if incoming is not None:
        incoming = {name.lower(): value for name, value in incoming.items()}
        project_origin = incoming.get("x-project-origin", project_origin)
        user_email = incoming.get("x-user-email", user_email)
    if user_email is None:
        logger.error("Per-request x-user-email is required for LLM calls")
        raise ValueError("Per-request x-user-email is required for LLM calls")
    headers = default_llm_headers(settings, user_email=user_email)
    if project_origin is not None:
        headers["x-project-origin"] = _header("x-project-origin", project_origin)
    return headers
