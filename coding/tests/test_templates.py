from __future__ import annotations

import asyncio
import importlib
import io
import json
import logging
import os
import re
import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import httpx
import pytest
import yaml
from pydantic import ValidationError

if TYPE_CHECKING:
    from ..assets.templates.llm.prompts import PromptSnapshot
    from ..assets.templates.utils.config import Settings

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_ROOT / "assets" / "templates"


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    root = tmp_path_factory.mktemp("coding-template-service")
    source = root / "src"
    source.mkdir()
    (source / "__init__.py").write_text('"""Isolated template service fixture."""\n', encoding="utf-8")
    for folder in ("llm", "utils"):
        shutil.copytree(TEMPLATES / folder, source / folder)
    existing = {name: module for name, module in sys.modules.items() if name == "src" or name.startswith("src.")}
    for name in existing:
        del sys.modules[name]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.syspath_prepend(str(root))
        try:
            yield SimpleNamespace(
                **{
                    name: importlib.import_module(f"src.{folder}.{name}")
                    for folder, name in (
                        ("utils", "config"),
                        ("utils", "logger"),
                        ("utils", "precheck"),
                        ("utils", "schemas"),
                        ("llm", "llm_headers"),
                        ("llm", "prompts"),
                        ("llm", "client"),
                        ("llm", "prompt"),
                        ("utils", "observability"),
                    )
                }
            )
        finally:
            for name in list(sys.modules):
                if name == "src" or name.startswith("src."):
                    del sys.modules[name]
            sys.modules.update(existing)


@pytest.fixture
def settings(bundle: SimpleNamespace, tmp_path: Path) -> Iterator[Settings]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "metadata:\n  urlName: template-project\n  business_owner_email: not-the-caller@example.invalid\n",
        encoding="utf-8",
    )
    with patch.dict(
        os.environ,
        {
            **{
                name: value
                for name, value in os.environ.items()
                if name.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "TEMP", "TMP"}
            },
            "MYSVC_PROJECT_ORIGIN": "template-origin",
            "MYSVC_LLM_MODEL": "test-model",
            "MYSVC_CONFIG_YAML_PATH": str(config_path),
        },
        clear=True,
    ):
        bundle.config.get_settings.cache_clear()
        try:
            yield bundle.config.get_settings()
        finally:
            bundle.config.get_settings.cache_clear()


@pytest.fixture
def captured_logs(bundle: SimpleNamespace, caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    loggers = [
        getattr(bundle, name).logger.logger
        for name in ("precheck", "llm_headers", "prompts", "client", "prompt", "observability")
    ]
    caplog.set_level(logging.WARNING)
    for custom in loggers:
        custom.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        for custom in loggers:
            custom.removeHandler(caplog.handler)


def test_skill_discovery_activation_and_resource_links() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = yaml.safe_load(skill.split("---", 2)[1])
    assert metadata["name"] == SKILL_ROOT.name == "coding"
    assert len(metadata["description"]) <= 1024
    assert "before every coding task" in metadata["description"]
    assert metadata["disable-model-invocation"] is False
    instruction = SKILL_ROOT.parents[2] / ".copilot" / "copilot-instructions.md"
    assert "Before starting any coding task" in instruction.read_text(encoding="utf-8")
    for document in [*SKILL_ROOT.rglob("*.md"), instruction]:
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if not target.startswith(("http:", "https:", "#")):
                assert (document.parent / target.split("#", 1)[0]).exists(), (document, target)
    assert sorted(path.name for path in (TEMPLATES / "llm").iterdir()) == [
        "client.py",
        "llm_headers.py",
        "prompt.py",
        "prompts.py",
        "prompts.yaml",
        "section_prompts.yaml",
    ]
    assert sorted(path.name for path in (TEMPLATES / "utils").iterdir()) == [
        "config.py",
        "logger.py",
        "observability.py",
        "precheck.py",
        "schemas.py",
    ]


def test_config_example_and_central_environment_contract(bundle: SimpleNamespace) -> None:
    example = (TEMPLATES / ".env.example").read_text(encoding="utf-8")
    keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", example, re.MULTILINE))
    assert keys == {bundle.config.PREFIX + name for name in bundle.config.ENV_DEFAULTS}
    for path in TEMPLATES.rglob("*.py"):
        if path.name != "config.py":
            assert not re.search(r"os\.(?:getenv|environ)", path.read_text(encoding="utf-8")), path
        assert not re.search(r"^\s*(?:from|import)\s+loguru\b", path.read_text(encoding="utf-8"), re.MULTILINE), path
    for name in ("precheck", "llm_headers", "prompts", "client", "prompt", "observability"):
        assert isinstance(getattr(bundle, name).logger, bundle.logger.CustomLogger)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PROJECT_ORIGIN", ""),
        ("LLM_MODEL", ""),
        ("LANGFUSE_ENABLED", "perhaps"),
        ("LANGFUSE_ENABLED", "true"),
        ("LANGFUSE_TRACING_ENABLED", "perhaps"),
        ("LLM_USE_RESPONSES_API", "perhaps"),
        ("LANGFUSE_PROMPT_CACHE_TTL_S", "-1"),
        ("LANGFUSE_PROMPT_CACHE_TTL_S", "1.5"),
        ("LLM_TIMEOUT_S", "0"),
        ("LLM_TIMEOUT_S", "-1"),
        ("LLM_TIMEOUT_S", "nan"),
        ("LLM_TIMEOUT_S", "inf"),
        ("LLM_TIMEOUT_S", "not-a-number"),
        ("LANGFUSE_TIMEOUT_S", "-1"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_MAX_RETRIES", "1.5"),
        ("PORT", "0"),
        ("PORT", "65536"),
        ("LOG_LEVEL", "invalid"),
        ("MODELS_API_BASE_URL", "file:///tmp/model"),
        ("MODELS_API_BASE_URL", "https://user:fake@model.example.invalid"),
        ("MODELS_API_BASE_URL", "https://model.example.invalid:invalid"),
    ],
)
def test_invalid_settings_name_the_variable(bundle: SimpleNamespace, settings: Settings, name: str, value: str) -> None:
    with patch.dict(os.environ, {"MYSVC_" + name: value}):
        expected = "MYSVC_LANGFUSE_BASE_URL" if name == "LANGFUSE_ENABLED" and value == "true" else "MYSVC_" + name
        with pytest.raises(bundle.config.ConfigError, match=expected):
            bundle.config.load_settings()


def test_settings_are_cached_and_immutable(bundle: SimpleNamespace, settings: Settings) -> None:
    with patch.dict(os.environ, {"MYSVC_PROJECT_ORIGIN": "later-origin"}):
        assert bundle.config.get_settings() is settings
    with pytest.raises(FrozenInstanceError):
        setattr(settings, "project_origin", "changed")


def test_startup_precheck_has_no_stale_failure_state(
    bundle: SimpleNamespace, settings: Settings, tmp_path: Path
) -> None:
    bundle.precheck.precheck_all(settings)
    for field in ("config_yaml_path", "prompts_path"):
        with pytest.raises(bundle.config.ConfigError):
            bundle.precheck.precheck_all(replace(settings, **{field: tmp_path / "missing"}))
    bundle.precheck.precheck_all(settings)


def test_headers_use_metadata_and_runtime_identity(bundle: SimpleNamespace, settings: Settings) -> None:
    assert bundle.llm_headers.resolve_llm_headers(settings, user_email="caller@example.invalid") == {
        "x-project-url": "template-project",
        "x-project-origin": "template-origin",
        "x-user-email": "caller@example.invalid",
    }
    incoming = bundle.llm_headers.resolve_llm_headers(
        settings,
        {
            "X-Project-Url": "must-not-override-metadata",
            "X-Project-Origin": "request-origin",
            "X-User-Email": "requester@example.invalid",
        },
    )
    assert incoming == {
        "x-project-url": "template-project",
        "x-project-origin": "request-origin",
        "x-user-email": "requester@example.invalid",
    }
    for value in (None, "", " ", "caller\r\ninjected"):
        with pytest.raises(ValueError, match="x-user-email"):
            bundle.llm_headers.resolve_llm_headers(settings, user_email=value)
    with pytest.raises(ValueError, match="x-project-origin"):
        bundle.llm_headers.resolve_llm_headers(
            settings, {"x-project-origin": "\n", "x-user-email": "caller@example.invalid"}
        )


def test_request_context_restores_after_failure_and_isolates_tasks(bundle: SimpleNamespace, settings: Settings) -> None:
    headers = bundle.llm_headers
    with headers.request_headers_scope({"x-user-email": "outer@example.invalid"}):
        with pytest.raises(RuntimeError), headers.request_headers_scope({"x-user-email": "inner@example.invalid"}):
            raise RuntimeError("fixture failure")
        assert headers.resolve_llm_headers(settings)["x-user-email"] == "outer@example.invalid"
    assert headers.current_request_headers() is None

    async def run() -> list[str]:
        async def caller(email: str) -> str:
            with headers.request_headers_scope({"x-user-email": email}):
                await asyncio.sleep(0)
                return headers.resolve_llm_headers(settings)["x-user-email"]

        return await asyncio.gather(caller("one@example.invalid"), caller("two@example.invalid"))

    assert asyncio.run(run()) == ["one@example.invalid", "two@example.invalid"]
    assert headers.current_request_headers() is None


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "text", "prompt": "Remote evidence contract", "version": 7},
        {"type": "chat", "prompt": [{"role": "system", "content": "Remote evidence contract"}], "version": 7},
    ],
)
def test_remote_prompt_success_does_not_require_local_fallback(
    bundle: SimpleNamespace, settings: Settings, tmp_path: Path, payload: dict[str, object]
) -> None:
    remote = replace(
        settings,
        langfuse_enabled=True,
        langfuse_base_url="https://prompts.example.invalid",
        prompts_path=tmp_path / "missing",
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    async def run() -> PromptSnapshot:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await bundle.prompts.PromptProvider(remote, client, auth=httpx.BasicAuth("fake", "fake")).load(
                "task-system"
            )

    result = asyncio.run(run())
    assert (result.text, result.source, result.version) == ("Remote evidence contract", "langfuse", 7)
    assert requests[0].url.path == "/api/public/v2/prompts/task-system"
    assert requests[0].url.params["label"] == "production"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"type": "text", "prompt": ""}),
        httpx.Response(200, json={"type": "text", "prompt": "text", "version": True}),
        httpx.Response(200, json={"type": "chat", "prompt": [{"role": "user", "content": "wrong role"}]}),
    ],
)
def test_remote_failure_is_logged_and_uses_bundled_prompt(
    bundle: SimpleNamespace, settings: Settings, response: httpx.Response, captured_logs: pytest.LogCaptureFixture
) -> None:
    remote = replace(settings, langfuse_enabled=True, langfuse_base_url="https://prompts.example.invalid")

    async def run() -> PromptSnapshot:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
            return await bundle.prompts.PromptProvider(remote, client, auth=httpx.BasicAuth("fake", "fake")).load(
                "task-system"
            )

    result = asyncio.run(run())
    assert result.source == "bundled"
    assert "supplied evidence" in result.text
    assert any("Remote prompt failed" in record.message for record in captured_logs.records)


def test_disabled_remote_never_calls_network_and_missing_fallback_raises(
    bundle: SimpleNamespace, settings: Settings
) -> None:
    def no_network(request: httpx.Request) -> httpx.Response:
        pytest.fail("Disabled remote prompts must not call the network")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
            provider = bundle.prompts.PromptProvider(settings, client)
            assert (await provider.load("task-system")).source == "bundled"
            with pytest.raises(bundle.prompts.PromptLoadError):
                await provider.load("not-bundled")
            with pytest.raises(bundle.prompts.PromptLoadError, match="credentials"):
                bundle.prompts.PromptProvider(replace(settings, langfuse_enabled=True), client)

    asyncio.run(run())


def test_chat_contract_accepts_flat_and_nested_without_mutating_history(bundle: SimpleNamespace) -> None:
    request = bundle.schemas.ChatRequest.model_validate(
        {
            "user_id": "test-user",
            "user_email": "caller@example.invalid",
            "prompt_id": 1,
            "user_message": "Current request",
            "chat_history": [{"role": "assistant", "content": "Earlier reply"}],
            "app_id": 1,
        }
    )
    nested = bundle.schemas.ChatRequest.model_validate(request.model_dump(by_alias=True))
    assert nested == request
    expected_chat = [
        {"role": "assistant", "content": "Earlier reply"},
        {"role": "user", "content": "Current request"},
    ]
    assert request.chat.full_chat == expected_chat
    assert request.chat.full_chat == expected_chat
    assert len(request.chat.full_chat) == 2
    assert len(request.chat.chat_history) == 1
    returned = request.chat.full_chat
    returned[0]["content"] = "Mutated copy"
    assert request.chat.chat_history[0]["content"] == "Earlier reply"
    assert (
        bundle.schemas.ChatDetails(user_message="one").session_id
        != bundle.schemas.ChatDetails(user_message="two").session_id
    )
    with pytest.raises(ValidationError):
        bundle.schemas.ChatRequest.model_validate({"user": {"user_id": "incomplete"}})
    with pytest.raises(ValidationError):
        bundle.schemas.FinalAnswerResponse(answer="answer", confidence_score=1.1)
    for invalid_history in ("", False, 0):
        payload = {
            "user_id": "test-user",
            "user_email": "caller@example.invalid",
            "prompt_id": 1,
            "user_message": "Current request",
            "chat_history": invalid_history,
            "app_id": 1,
        }
        with pytest.raises(ValidationError):
            bundle.schemas.ChatRequest.model_validate(payload)


@pytest.mark.parametrize(
    "message",
    ['{"password": "fake-value"}', "token=fake-value", "Authorization: Bearer fake-value", "Bearer fake-value"],
)
def test_common_credential_messages_are_redacted(bundle: SimpleNamespace, message: str) -> None:
    assert "fake-value" not in bundle.logger.redact(message)
    assert bundle.logger.redact("operation completed") == "operation completed"


def test_model_client_uses_per_request_headers_and_explicit_settings(
    bundle: SimpleNamespace, settings: Settings
) -> None:
    configured = replace(
        settings,
        llm_timeout_s=12,
        llm_max_retries=2,
        llm_reasoning_effort="low",
        llm_use_responses_api=True,
    )
    with bundle.llm_headers.request_headers_scope({"x-user-email": "one@example.invalid"}):
        first = bundle.client.build_configured_llm(configured, api_key="offline-placeholder")
    second = bundle.client.build_configured_llm(
        configured, api_key="offline-placeholder", user_email="two@example.invalid"
    )
    assert first is not second
    assert first.default_headers["x-user-email"] == "one@example.invalid"
    assert second.default_headers["x-user-email"] == "two@example.invalid"
    assert second.default_headers["x-project-url"] == "template-project"
    assert second.openai_api_base == settings.models_api_base_url
    assert second.model_name == settings.llm_model
    assert second.request_timeout == 12
    assert second.max_retries == 2
    assert second.reasoning_effort == "low"
    assert second.use_responses_api is True
    assert bundle.client.llm_call_metadata(configured, section="summary", user_email="two@example.invalid") == {
        "model": settings.llm_model,
        "reasoning_effort": "low",
        "report_section": "summary",
        "langfuse_user_id": "two@example.invalid",
    }
    with pytest.raises(ValueError, match="credential"):
        bundle.client.build_configured_llm(settings, api_key="", user_email="one@example.invalid")
    with pytest.raises(ValueError, match="x-user-email"):
        bundle.client.build_configured_llm(settings, api_key="offline-placeholder")


def test_section_prompt_bundle_and_literal_payload_replacement(bundle: SimpleNamespace, settings: Settings) -> None:
    snapshot = bundle.prompt.SectionPromptProvider(settings).load()
    assert snapshot.source == "bundled"
    assert set(snapshot.sections) == {"assessment", "recommendations", "summary"}
    payload = '{"nested": {"value": "{not-a-format-variable}"}}'
    assert snapshot.sections["summary"].render_user(payload) == f"Summarize this payload:\n{payload}\n"
    assert "supplied payload" in snapshot.system_for("summary")
    assert "Summarize the evidence" in snapshot.system_for("summary")
    with pytest.raises(TypeError):
        snapshot.sections["extra"] = snapshot.sections["summary"]


@pytest.mark.parametrize("failure", [None, "fetch", "compile", "invalid"])
def test_section_prompt_remote_contract_and_logged_fallback(
    bundle: SimpleNamespace, settings: Settings, failure: str | None, captured_logs: pytest.LogCaptureFixture
) -> None:
    settings = replace(settings, langfuse_enabled=True, langfuse_prompt_cache_ttl_s=23, langfuse_timeout_s=2.5)
    document = yaml.safe_load(settings.section_prompt_path.read_text(encoding="utf-8"))
    document["system_preamble"] = "Remote report contract"
    calls: list[dict[str, object]] = []

    class RemotePrompt:
        is_fallback = False
        version = 4

        def compile(self, **variables: object) -> str:
            if failure == "compile":
                raise RuntimeError("Fake compile failure")
            return "system_preamble: stale\nsections: {}" if failure == "invalid" else yaml.safe_dump(document)

    class RemoteClient:
        def get_prompt(self, name: str, **kwargs: object) -> RemotePrompt:
            calls.append({"name": name, **kwargs})
            if failure == "fetch":
                raise RuntimeError("Fake fetch failure")
            return RemotePrompt()

    snapshot = bundle.prompt.SectionPromptProvider(settings, client=RemoteClient()).load()
    assert snapshot.source == ("langfuse" if failure is None else "bundled")
    assert snapshot.prompt_version == (4 if failure is None else None)
    assert calls == [
        {
            "name": "sectioned-report",
            "label": "production",
            "type": "text",
            "cache_ttl_seconds": 23,
            "max_retries": 3,
            "fetch_timeout_seconds": 3,
        }
    ]
    assert bool(captured_logs.records) == (failure is not None)


def test_section_prompt_fails_when_no_valid_source_exists(
    bundle: SimpleNamespace, settings: Settings, tmp_path: Path
) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("system_preamble: ''\nsections: {}", encoding="utf-8")
    for path in (invalid, tmp_path / "missing.yaml"):
        with pytest.raises(bundle.prompt.SectionPromptLoadError):
            bundle.prompt.SectionPromptProvider(replace(settings, section_prompt_path=path)).load()
    with pytest.raises(bundle.prompt.SectionPromptLoadError, match="authenticated"):
        bundle.prompt.SectionPromptProvider(replace(settings, langfuse_enabled=True))


def test_trace_sanitizer_preserves_usage_and_masks_nested_values(bundle: SimpleNamespace) -> None:
    value = {
        "api-key": "offline-placeholder",
        "source_code": "private code",
        "nested": [{"password": "offline-placeholder", "input_tokens": 5}],
        "json": '{"secret":"offline-placeholder","output_tokens":3}',
        "binary": b"private",
        "error": RuntimeError("Do not export exception text"),
        "nan": float("nan"),
    }
    sanitized = bundle.observability.sanitize_trace_value(value)
    assert sanitized["api-key"] == "[REDACTED]"
    assert sanitized["source_code"] == "[REDACTED]"
    assert sanitized["nested"] == [{"password": "[REDACTED]", "input_tokens": 5}]
    assert json.loads(sanitized["json"]) == {"secret": "[REDACTED]", "output_tokens": 3}
    assert sanitized["binary"] == {"content_type": "binary", "size_bytes": 7}
    assert sanitized["error"] == "RuntimeError"
    assert sanitized["nan"] is None
    assert bundle.observability.mask_trace_data(data=value) == sanitized
    assert bundle.observability.sanitize_trace_value('{"password": incomplete') == "[REDACTED: invalid structured text]"


def test_trace_context_preserves_business_exception_and_closes_resources(bundle: SimpleNamespace) -> None:
    updates: list[dict[str, object]] = []
    events: list[str] = []

    class FakeSpan:
        def update(self, **kwargs: object) -> None:
            updates.append(kwargs)

    class FakeClient:
        @contextmanager
        def start_as_current_observation(self, **kwargs: object) -> Iterator[FakeSpan]:
            events.append("span-open")
            try:
                yield FakeSpan()
            finally:
                events.append("span-close")

        def flush(self) -> None:
            events.append("flush")

    @contextmanager
    def propagate(**kwargs: object) -> Iterator[None]:
        assert kwargs == {"session_id": "session-1", "user_id": "user-1"}
        events.append("attributes-open")
        try:
            yield
        finally:
            events.append("attributes-close")

    runtime = bundle.observability.Observability(client=FakeClient(), propagate=propagate)
    error = RuntimeError("business failure")
    with (
        pytest.raises(RuntimeError) as caught,
        runtime.observation(
            "request",
            input_data={"password": "offline-placeholder"},
            metadata={"langfuse_session_id": "session-1", "langfuse_user_id": "user-1"},
        ) as span,
    ):
        bundle.observability.record_output(span, {"status": "FAILED", "secret": "offline-placeholder"})
        raise error
    assert caught.value is error
    assert events == ["span-open", "attributes-open", "attributes-close", "span-close"]
    assert updates[0]["input"] == {"password": "[REDACTED]"}
    assert updates[1]["output"] == {"status": "FAILED", "secret": "[REDACTED]"}
    assert updates[-1] == {"level": "ERROR", "status_message": "RuntimeError"}
    runtime.flush()
    assert events[-1] == "flush"


def test_optional_tracing_failures_warn_without_replacing_business_work(
    bundle: SimpleNamespace, captured_logs: pytest.LogCaptureFixture
) -> None:
    class FailingSpan:
        def update(self, **kwargs: object) -> None:
            raise RuntimeError("Fake update failure")

    class FailingClient:
        @contextmanager
        def start_as_current_observation(self, **kwargs: object) -> Iterator[FailingSpan]:
            try:
                yield FailingSpan()
            finally:
                raise RuntimeError("Fake cleanup failure")

        def flush(self) -> None:
            raise RuntimeError("Fake flush failure")

    runtime = bundle.observability.Observability(client=FailingClient())
    with runtime.observation("request", input_data={}, metadata={}) as span:
        assert span is None
    bundle.observability.record_output(FailingSpan(), {})
    bundle.observability.record_error(FailingSpan(), "failed")
    runtime.flush()
    assert len(captured_logs.records) == 5


def test_trace_configuration_is_explicit_and_does_not_export(
    bundle: SimpleNamespace, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert bundle.observability.configure_observability(settings).client is None
    enabled = replace(settings, langfuse_tracing_enabled=True, langfuse_base_url="https://trace.example.invalid")
    with pytest.raises(ValueError, match="credentials"):
        bundle.observability.configure_observability(enabled)
    calls: list[dict[str, object]] = []
    callback = object()

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    def make_callback(**kwargs: object) -> object:
        assert kwargs == {"public_key": "offline-public"}
        return callback

    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(Langfuse=FakeClient, propagate_attributes=None))
    monkeypatch.setitem(sys.modules, "langfuse.langchain", SimpleNamespace(CallbackHandler=make_callback))
    runtime = bundle.observability.configure_observability(
        enabled, public_key="offline-public", secret_key="offline-secret"
    )
    assert runtime.callbacks == (callback,)
    assert calls[0]["base_url"] == enabled.langfuse_base_url
    assert calls[0]["mask"] is bundle.observability.mask_trace_data
    kwargs = bundle.observability.build_ainvoke_kwargs(
        {"x-user-email": "caller@example.invalid"}, runtime, metadata={"secret": "private", "input_tokens": 7}
    )
    assert kwargs["config"]["callbacks"] == [callback]
    assert kwargs["config"]["metadata"] == {"secret": "[REDACTED]", "input_tokens": 7}
    assert bundle.observability.build_ainvoke_kwargs({}, bundle.observability.Observability()) == {"extra_headers": {}}


def test_governance_logger_patterns_are_merged(bundle: SimpleNamespace) -> None:
    token = "x" * 120
    url = "https://" + "sample-user:sample-password" + "@example.invalid/repository"
    assert "sample-password" not in bundle.logger.redact(url)
    assert token not in bundle.logger.redact(token)
    assert bundle.logger.redact("ordinary operation") == "ordinary operation"


def test_custom_logger_levels_redaction_and_exception_contract(bundle: SimpleNamespace) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    underlying = logging.getLogger("coding-skill-custom-logger-test")
    underlying.addHandler(handler)
    underlying.propagate = False
    custom = bundle.logger.CustomLogger(underlying.name)
    try:
        custom.set_level(logging.DEBUG)
        assert underlying.level == handler.level == logging.DEBUG
        custom.debug("token=offline-placeholder")
        assert "offline-placeholder" not in stream.getvalue()
        assert "[REDACTED]" in stream.getvalue()
        with pytest.warns(UserWarning, match="outside of an active exception"):
            custom.exception("No active error")
        assert "NoneType: None" not in stream.getvalue()
        error = RuntimeError("Business failure")
        with pytest.raises(RuntimeError) as caught, custom:
            raise error
        assert caught.value is error
        assert "Unhandled exception in CustomLogger context" in stream.getvalue()
    finally:
        underlying.removeHandler(handler)
        handler.close()
