# Reusable LLM and utilities templates

These are sanitized adaptations of InfraSense's `src/llm` and `src/utils`, extended with governance-orch's
`src/llm/client.py`, `src/llm/prompt.py`, `src/utils/observability.py`, and the user's custom logger file.
The working source folders remain unchanged. This bundle is scaffolding, not an installed service or
a replacement for authentication middleware and the platform secrets provider.

## Layout and adoption

Copy only missing, approved components from `llm/` and `utils/` into the target service's `src/llm/`
and `src/utils/`. Imports assume that layout and execution from the service root. Preserve an existing
project's packaging and config module instead of installing a parallel configuration system.

1. Inspect the repository's runtime, dependency manifest, helpers, tests, and platform contracts.
2. For a new service, copy [.env.example](./.env.example) to its root and replace `MYSVC_` in both
   [config.py](./utils/config.py) and the example. Set the required project origin and model explicitly.
3. Use the repository's compatible versions of `httpx`, `PyYAML`, `pydantic` v2, and
   `typing_extensions`. Do not upgrade the runtime or install unrelated packages. The templates use
   Python 3.11-compatible syntax; the service manifest remains authoritative.
4. Export the documented environment variables through the existing launcher/deployment system. These
   templates do not automatically load a `.env` file. Call `get_settings()` at startup, then
   `precheck_all(settings)` before accepting traffic. Use `CustomLogger(__name__)` from `src.utils.logger`
   for every Python module and configure each service logger's level at startup through
   `logger.set_level(logging.getLevelNamesMapping()[settings.log_level])` on each logger instance.
   Pass the same immutable settings snapshot to the LLM helpers.
5. Supply the service's real `config.yaml` with `metadata.urlName`. No production metadata is bundled.
   `resolve_llm_headers` requires a runtime user email from the authenticated request, directly or through
   `request_headers_scope`; it never substitutes a business owner. Request context is not authentication.
6. Resolve configured secret *names* through `scutils` or the current Snippet 77 secrets provider.
   No secret values belong in settings, `.env.example`, prompt YAML, or logs. Construct `httpx.BasicAuth`
   from the resolved Langfuse keys and pass it to `PromptProvider` with an application-managed async client.
   Keep TLS verification enabled and manage the client's lifetime at the application boundary.
7. Remote prompts are disabled by default. If enabled, configure the base URL and credentials. A successful
   remote fetch does not require a valid local file at fetch time; an outage or invalid remote response
   logs a warning and uses the named bundled prompt. An unusable fallback raises `PromptLoadError`.
   Startup precheck still requires the bundled file to exist so an outage fallback is available.
8. Replace the generic `task-system` prompt with task-specific evidence and output contracts. Its YAML key
   must match the remote prompt name. The prompt label is configured centrally, not duplicated in YAML.
9. Adapt and run the [offline template tests](../../tests/test_templates.py) alongside the target's
   existing tests. Verify current Langfuse and internal platform APIs before enabling production traffic.

## Additional governance-orch templates

| File | Purpose | Adoption boundary |
|---|---|---|
| [client.py](./llm/client.py) | Construct an OpenAI-compatible LangChain model and call metadata | Resolve the API key through the existing secrets provider; build for one authenticated request, never cache its identity globally. |
| [prompt.py](./llm/prompt.py) | Load and validate a sectioned report from Langfuse or a bundled YAML fallback | Supply an authenticated SDK client when remote prompts are enabled; this is separate from the simple async loader in `prompts.py`. |
| [section_prompts.yaml](./llm/section_prompts.yaml) | Generic assessment/recommendations/summary contract | Change the YAML and `SECTION_NAMES` together for a different report contract. JSON braces are preserved by literal payload replacement. |
| [observability.py](./utils/observability.py) | Optional spans, callback configuration, output/error recording, flushing, and trace-data masking | Configure once at startup, pass the resulting `Observability` instance explicitly, and call `flush()` during shutdown. |
| [logger.py](./utils/logger.py) | The user's standard-library-backed `CustomLogger` implementation | Canonical logger copied from governance-orch, with credential redaction, UTF-8 output, level control, and exception/context-manager support. Do not substitute Loguru. |

The model client uses the configured API root exactly; set `/v1` where required rather than appending it
blindly. Timeout, retries, reasoning effort, and Responses API selection come from settings. Verify both
the selected model and gateway support before enabling reasoning or Responses API mode. Constructing a
client is not a model call; use the target's existing `ainvoke` / structured-output orchestration.

For sectioned prompts, inject an authenticated Langfuse SDK client constructed at the service boundary from
the configured secret names, base URL, and timeout. A supplied client is ignored when remote prompts are off.
Remote fetch/compile/validation failures are logged and use the local fallback; if neither source is valid,
`SectionPromptLoadError` is raised. The synchronous loader should not block an async request's event loop:
reuse the target's worker/thread boundary or its async prompt adapter.

Tracing is independently controlled by `MYSVC_LANGFUSE_TRACING_ENABLED` and disabled by default. Resolve
the keys and pass them explicitly to `configure_observability`. Enabled tracing with missing credentials
is a startup configuration error. SDK initialization, span, update, cleanup, and flush failures log a warning
and do not replace business results or suppress application exceptions. `Observability.observation` nests
spans and propagates the supplied `langfuse_session_id` / `langfuse_user_id` to child observations.
Use authenticated identities only; traces and metadata can still contain personal or confidential data.

`build_ainvoke_kwargs` adds callbacks and sanitized metadata only when tracing callbacks exist. It copies
the caller's headers. Use headers from `resolve_llm_headers`; metadata redaction does not authenticate a caller.
The sanitizers redact known credential keys, source excerpts, URL userinfo, common credential strings,
and long opaque tokens while retaining numeric token usage. Exception objects retain only their type.
They are defense in depth, not a guarantee that arbitrary source code, PII, or free-form text is safe to export.
The SDK `mask` hook covers SDK-managed data; review export-stage masking for third-party OpenTelemetry
instrumentation before enabling additional integrations.

### Verified SDK boundary (2026-10-26)

Offline construction/signature checks use the existing local `langchain-openai` 1.6.0, `langchain-core`
1.6.0, and `langfuse` 4.14.4 environment. No SDK upgrade is implied. Current Langfuse documentation
describes newer majors, so check SDK/server compatibility for the target deployment before adoption.

- [LangChain ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai):
  model construction, custom API roots, timeout/retries, reasoning.
- [Langfuse Python API reference](https://python.reference.langfuse.com/langfuse):
  client construction, text prompt retrieval, and observation interfaces.
- [Langfuse instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation):
  observation context managers and attribute propagation.
- [Langfuse masking](https://langfuse.com/docs/observability/features/masking):
  SDK `mask` versus export-stage `mask_otel_spans`.
- [Langfuse SDK compatibility](https://langfuse.com/docs/observability/sdk/overview):
  current SDK/server compatibility guidance.

## Offline validation

Use an existing Python environment with the template dependencies above and `pytest`. From PowerShell:

```powershell
python -m pytest --noconftest --rootdir "$HOME\.agents\skills\coding" -o addopts= "$HOME\.agents\skills\coding\tests\test_templates.py"
```

The tests copy the templates into an isolated temporary service layout and use HTTPX mock transports;
they do not call the Models API or Langfuse. The original project folders are not imported or modified.
Keep these bundle tests with the skill; adapt the behavioral cases into the target service's own tests.
Client tests also require the target's compatible `langchain-openai` package; tracing configuration tests
use SDK doubles and do not export telemetry. SDKs remain optional when their templates are not adopted.
The supplied custom logger is retained verbatim (line endings aside), including its original long
docstrings. It is excluded from autoformatting and the line-length lint rule. Its original `__exit__`
annotation permits an optional exception value where `logging.exception`'s type expects a concrete
exception; this is an existing static diagnostic, not a new adapter behavior. Type-check new adapters
separately rather than silently rewriting the user's logger.

## Deliberate differences from the source

- No InfraSense names, VM inventory, private hosts, embedded credentials, or vCenter-specific checks.
  Add service-specific prechecks at the real startup boundary if the task requires them.
- One frozen, validated settings snapshot; strict booleans and finite positive timeouts; secret names only.
  The old `references/config_template.py` and `references/env.example` now live in this bundle.
- The supplied `CustomLogger` file is the canonical Python logging implementation, not a new wrapper.
  Every logging template imports it and passes one preformatted message. It redacts common credential
  patterns in messages and preserves its existing exception behavior. This is not a comprehensive scrubber
  for exception text or structured payloads:
  never log raw credentials, authorization headers, request bodies, or secret-bearing exceptions.
- Headers use configured metadata and per-request identity; missing or newline-containing values fail.
- Prompt loading uses configured paths and timeouts, explicit credentials, and an injected HTTP client.
  Mocked tests validate this adapter, not the availability or compatibility of a live Langfuse deployment.
- Schema session IDs are generated per instance; `full_chat` does not mutate stored history; both flat and
  nested input shapes validate. The generic contract uses typed message dictionaries; a LangChain-specific
  `messages` conversion belongs in the target service's existing adapter, not a mandatory template dependency.
- Prechecks raise on failure instead of returning an easily ignored false value. Callers must not continue
  startup after a failure.

## Scope boundaries

The bundle now includes model construction and optional tracing adapters, but does not execute a report
pipeline, authorize users, resolve secrets, access databases, or configure deployments. Model request
retries are delegated to the installed SDK using the configured retry budget.
Wire those through existing platform integrations rather than assuming that copying the folders completes
EAP compliance. Never add the `"All"` connector-group convention to a non-EAP authorization system without
verifying its contract; request-provided identity/groups must be authenticated by the service.
