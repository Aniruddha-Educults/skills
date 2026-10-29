from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

import yaml
from src.utils.config import Settings

from src.utils.logger import CustomLogger

logger = CustomLogger(__name__)

SECTION_NAMES = ("assessment", "recommendations", "summary")


class SectionPromptLoadError(RuntimeError):
    pass


class TextPrompt(Protocol):
    is_fallback: bool
    version: int

    def compile(self, **variables: object) -> str: ...


class PromptClient(Protocol):
    def get_prompt(
        self,
        name: str,
        *,
        label: str,
        type: Literal["text"],
        cache_ttl_seconds: int,
        max_retries: int,
        fetch_timeout_seconds: int,
    ) -> TextPrompt: ...


@dataclass(frozen=True, slots=True)
class SectionPrompt:
    instruction: str
    user_template: str

    def render_user(self, payload_json: str) -> str:
        return self.user_template.replace("{payload}", payload_json)


@dataclass(frozen=True, slots=True)
class SectionPromptSnapshot:
    system_preamble: str
    sections: Mapping[str, SectionPrompt]
    source: Literal["langfuse", "bundled"]
    prompt_name: str
    prompt_label: str
    prompt_version: int | None = None

    def system_for(self, section: str) -> str:
        return f"{self.system_preamble.strip()}\n\n{self.sections[section].instruction.strip()}"


def _validate(text: str) -> tuple[str, Mapping[str, SectionPrompt]]:
    raw: object = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("Section prompt must be an object")
    preamble = raw.get("system_preamble")
    sections_raw = raw.get("sections")
    if not isinstance(preamble, str) or not preamble.strip() or not isinstance(sections_raw, dict):
        raise ValueError("Section prompt must define a nonempty system_preamble and sections")
    sections: dict[str, SectionPrompt] = {}
    for name in SECTION_NAMES:
        entry = sections_raw.get(name)
        if not isinstance(entry, dict):
            raise ValueError(f"Missing section '{name}'")
        instruction, template = entry.get("instruction"), entry.get("user_template")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"Missing instruction for section '{name}'")
        if not isinstance(template, str) or "{payload}" not in template:
            raise ValueError(f"Section '{name}' user_template must include '{{payload}}'")
        sections[name] = SectionPrompt(instruction=instruction, user_template=template)
    return preamble, MappingProxyType(sections)


class SectionPromptProvider:
    def __init__(self, settings: Settings, *, client: PromptClient | None = None) -> None:
        self._settings = settings
        self._client = client
        if settings.langfuse_enabled and client is None:
            logger.error("Remote section prompts enabled without an authenticated prompt client")
            raise SectionPromptLoadError("Provide an authenticated Langfuse prompt client")

    def load(self) -> SectionPromptSnapshot:
        settings = self._settings
        if settings.langfuse_enabled and self._client is not None:
            try:
                prompt = self._client.get_prompt(
                    settings.section_prompt_name,
                    label=settings.langfuse_prompt_label,
                    type="text",
                    cache_ttl_seconds=settings.langfuse_prompt_cache_ttl_s,
                    max_retries=settings.llm_max_retries,
                    fetch_timeout_seconds=math.ceil(settings.langfuse_timeout_s),
                )
                preamble, sections = _validate(prompt.compile())
                version = prompt.version
                if type(version) is not int or version < 1:
                    raise ValueError("Remote prompt version must be a positive integer")
                source: Literal["langfuse", "bundled"] = "bundled" if prompt.is_fallback else "langfuse"
                logger.info(f"Section prompt loaded: source='{source}'")
                return SectionPromptSnapshot(
                    preamble,
                    sections,
                    source,
                    settings.section_prompt_name,
                    settings.langfuse_prompt_label,
                    version if source == "langfuse" else None,
                )
            except Exception as exc:
                logger.warning(f"Remote section prompt failed: error_type='{type(exc).__name__}'; using bundled prompt")
        try:
            preamble, sections = _validate(settings.section_prompt_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, ValueError, TypeError):
            logger.error("No valid bundled section prompt")
            raise SectionPromptLoadError("No valid bundled section prompt") from None
        logger.info("Section prompt loaded: source='bundled'")
        return SectionPromptSnapshot(
            preamble, sections, "bundled", settings.section_prompt_name, settings.langfuse_prompt_label
        )
