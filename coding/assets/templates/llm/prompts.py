from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx
import yaml
from src.utils.config import Settings

from src.utils.logger import CustomLogger

logger = CustomLogger(__name__)


class PromptLoadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptSnapshot:
    name: str
    text: str
    source: Literal["bundled", "langfuse"]
    version: int | None = None


class PromptProvider:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient,
        *,
        auth: httpx.BasicAuth | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._auth = auth
        if settings.langfuse_enabled and auth is None:
            logger.error("Remote prompts enabled without resolved Langfuse credentials")
            raise PromptLoadError("Resolve Langfuse credentials through the platform secrets provider")

    async def load(self, name: str) -> PromptSnapshot:
        if not name.strip():
            logger.error("Prompt name must not be empty")
            raise PromptLoadError("Prompt name must not be empty")
        if self._settings.langfuse_enabled:
            try:
                prompt = await self._fetch_remote(name)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                logger.warning(f"Remote prompt failed: name='{name}' error_type='{type(exc).__name__}'")
            else:
                logger.info(f"Prompt loaded: name='{name}' source='langfuse'")
                return prompt
        text = self._fallback(name)
        logger.info(f"Prompt loaded: name='{name}' source='bundled'")
        return PromptSnapshot(name=name, text=text, source="bundled")

    def _fallback(self, name: str) -> str:
        try:
            raw = yaml.safe_load(self._settings.prompts_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get(name), dict):
                raise ValueError("Missing bundled prompt")
            text = raw[name].get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty bundled prompt")
        except (OSError, ValueError, yaml.YAMLError):
            logger.error(f"No valid bundled prompt: name='{name}'")
            raise PromptLoadError(f"No valid bundled fallback exists for prompt '{name}'") from None
        return text

    async def _fetch_remote(self, name: str) -> PromptSnapshot:
        url = f"{self._settings.langfuse_base_url}/api/public/v2/prompts/{quote(name, safe='')}"
        response = await self._client.get(
            url,
            params={"label": self._settings.langfuse_prompt_label},
            auth=self._auth,
            timeout=self._settings.langfuse_timeout_s,
        )
        response.raise_for_status()
        payload: object = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Prompt response must be an object")
        if payload.get("type") == "text":
            text = payload.get("prompt")
        elif payload.get("type") == "chat":
            messages = payload.get("prompt")
            if not isinstance(messages, list) or len(messages) != 1:
                raise ValueError("Chat prompts must contain exactly one system message")
            message = messages[0]
            if not isinstance(message, dict) or message.get("role") != "system":
                raise ValueError("Chat prompts must contain exactly one system message")
            text = message.get("content")
        else:
            raise ValueError("Unsupported prompt type")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Prompt text must not be empty")
        version = payload.get("version")
        if version is not None and (type(version) is not int or version < 1):
            raise ValueError("Prompt version must be a positive integer")
        return PromptSnapshot(name=name, text=text, source="langfuse", version=version)
