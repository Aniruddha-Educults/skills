from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import SecretStr
from src.llm.llm_headers import resolve_llm_headers
from src.utils.config import Settings

from src.utils.logger import CustomLogger

logger = CustomLogger(__name__)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


def build_configured_llm(settings: Settings, *, api_key: str, user_email: str | None = None) -> ChatOpenAI:
    """Build for one authenticated request; never cache user headers in a process singleton."""
    if not api_key.strip():
        logger.error("Resolved Models API credential must not be empty")
        raise ValueError("Resolve the Models API credential through the platform secrets provider")
    headers = resolve_llm_headers(settings, user_email=user_email)
    from langchain_openai import ChatOpenAI

    logger.info(f"Building request-scoped chat model '{settings.llm_model}'")
    return ChatOpenAI(
        base_url=settings.models_api_base_url,
        api_key=SecretStr(api_key),
        model=settings.llm_model,
        default_headers=headers,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        reasoning_effort=settings.llm_reasoning_effort,
        use_responses_api=settings.llm_use_responses_api,
    )


def llm_call_metadata(
    settings: Settings, *, user_email: str | None = None, section: str | None = None
) -> dict[str, str]:
    metadata = {"model": settings.llm_model}
    if settings.llm_reasoning_effort:
        metadata["reasoning_effort"] = settings.llm_reasoning_effort
    if section:
        metadata["report_section"] = section
    if user_email:
        metadata["langfuse_user_id"] = user_email
    return metadata
