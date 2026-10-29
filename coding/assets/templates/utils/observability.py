from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, TypedDict

from src.utils.config import Settings

from src.utils.logger import CustomLogger, redact

logger = CustomLogger(__name__)

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.runnables import RunnableConfig

TraceValue: TypeAlias = bool | int | float | str | None | list["TraceValue"] | dict[str, "TraceValue"]
_SENSITIVE_KEYWORDS = ("api_key", "authorization", "password", "secret", "token")
_SENSITIVE_FIELDS = {"value", "default", "excerpt", "source_code"}
_USAGE_FIELDS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "reasoning_tokens",
}


class Span(Protocol):
    def update(
        self,
        *,
        input: TraceValue = None,
        output: TraceValue = None,
        metadata: TraceValue = None,
        level: Literal["ERROR"] | None = None,
        status_message: str | None = None,
    ) -> object: ...


class TraceClient(Protocol):
    def start_as_current_observation(self, *, as_type: Literal["span"], name: str) -> AbstractContextManager[Span]: ...

    def flush(self) -> object: ...


def sanitize_trace_value(value: object, *, key: str | None = None) -> TraceValue:
    normalized = key.lower().replace("-", "_") if key else ""
    if normalized in _USAGE_FIELDS and type(value) in {int, float}:
        return value if isinstance(value, int) or isinstance(value, float) and math.isfinite(value) else None
    if normalized in _SENSITIVE_FIELDS or any(word in normalized for word in _SENSITIVE_KEYWORDS):
        return "[REDACTED]"
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return sanitize_trace_value(model_dump(mode="json"), key=key)
    if is_dataclass(value) and not isinstance(value, type):
        return sanitize_trace_value(asdict(value), key=key)
    if isinstance(value, Mapping):
        return {str(k): sanitize_trace_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitize_trace_value(item) for item in value]
    if isinstance(value, bytes | bytearray):
        return {"content_type": "binary", "size_bytes": len(value)}
    if isinstance(value, BaseException):
        return type(value).__name__
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except ValueError:
                return "[REDACTED: invalid structured text]"
            return json.dumps(sanitize_trace_value(parsed))
        return redact(value)
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return f"<{type(value).__name__}>"


def mask_trace_data(*, data: object, **kwargs: object) -> TraceValue:
    return sanitize_trace_value(data)


@dataclass(frozen=True, slots=True)
class Observability:
    client: TraceClient | None = None
    callbacks: tuple[BaseCallbackHandler, ...] = ()
    propagate: Callable[..., AbstractContextManager[object]] | None = None

    @contextmanager
    def observation(
        self, name: str, *, input_data: Mapping[str, object], metadata: Mapping[str, object]
    ) -> Iterator[Span | None]:
        if self.client is None:
            yield None
            return
        stack = ExitStack()
        span: Span | None = None
        try:
            candidate = stack.enter_context(self.client.start_as_current_observation(as_type="span", name=name))
            if self.propagate is not None:
                stack.enter_context(
                    self.propagate(
                        session_id=metadata.get("langfuse_session_id"),
                        user_id=metadata.get("langfuse_user_id"),
                    )
                )
            candidate.update(input=sanitize_trace_value(input_data), metadata=sanitize_trace_value(metadata))
            span = candidate
        except Exception as exc:
            logger.warning(f"Trace initialization failed: error_type='{type(exc).__name__}'")
        try:
            yield span
        except BaseException as exc:
            record_error(span, type(exc).__name__)
            raise
        finally:
            try:
                stack.close()
            except Exception as exc:
                logger.warning(f"Trace cleanup failed: error_type='{type(exc).__name__}'")

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception as exc:
                logger.warning(f"Trace flush failed: error_type='{type(exc).__name__}'")


def configure_observability(
    settings: Settings, *, public_key: str | None = None, secret_key: str | None = None
) -> Observability:
    if not settings.langfuse_tracing_enabled:
        logger.info("Langfuse tracing disabled")
        return Observability()
    if not public_key or not public_key.strip() or not secret_key or not secret_key.strip():
        logger.error("Tracing enabled without resolved Langfuse credentials")
        raise ValueError("Resolve Langfuse credentials before configuring tracing")
    try:
        from langfuse import Langfuse, propagate_attributes
        from langfuse.langchain import CallbackHandler

        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=settings.langfuse_base_url,
            environment=settings.environment,
            timeout=math.ceil(settings.langfuse_timeout_s),
            mask=mask_trace_data,
        )
        handler = CallbackHandler(public_key=public_key)
    except Exception as exc:
        logger.warning(f"Langfuse initialization failed; tracing disabled: error_type='{type(exc).__name__}'")
        return Observability()
    logger.info("Langfuse tracing enabled")
    return Observability(client, (handler,), propagate_attributes)


def record_output(span: Span | None, output: object) -> None:
    if span is None:
        return
    try:
        span.update(output=sanitize_trace_value(output))
        if isinstance(output, Mapping) and any(
            str(output.get(key)).upper() in {"ERROR", "FAILED"}
            for key in ("overall_status", "analysis_status", "status")
        ):
            record_error(span, "Operation failed")
    except Exception as exc:
        logger.warning(f"Trace output update failed: error_type='{type(exc).__name__}'")


def record_error(span: Span | None, error: object) -> None:
    if span is None:
        return
    try:
        span.update(level="ERROR", status_message=str(sanitize_trace_value(error)))
    except Exception as exc:
        logger.warning(f"Trace error update failed: error_type='{type(exc).__name__}'")


class InvokeKwargs(TypedDict, total=False):
    extra_headers: dict[str, str]
    config: RunnableConfig


def build_ainvoke_kwargs(
    extra_headers: Mapping[str, str], observability: Observability, *, metadata: Mapping[str, object] | None = None
) -> InvokeKwargs:
    kwargs: InvokeKwargs = {"extra_headers": dict(extra_headers)}
    if observability.callbacks:
        config: RunnableConfig = {"callbacks": list(observability.callbacks)}
        if metadata:
            config["metadata"] = {key: sanitize_trace_value(value, key=key) for key, value in metadata.items()}
        kwargs["config"] = config
    return kwargs
