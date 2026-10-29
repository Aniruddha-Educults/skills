---
name: coding
description: "Load before every coding task: implementation, scaffolding, bug fixes, debugging, refactoring, code review, tests, scripts, configuration changes, and UI work. Verification-first engineering workflow: clarify, verify, plan, approve when gated, execute, validate. Maintain living repository understanding and change/decision docs explaining what changed and why. Includes central typed environment configuration, the user's CustomLogger (not Loguru), IT-GenAI-CoE/EAP conventions, reusable llm and utils templates, test-quality gates, and UI polish. Apply stack-specific rules only to matching projects; preserve existing runtimes and architecture."
metadata:
  version: "1.3.0"
  skill_category: Coding
  skill_tags: [governance, backend, testing, ui-polish, verification, documentation]
  visibility: shared
user-invocable: true
disable-model-invocation: false
---

# Coding Skill (AOP Engineering)

## Purpose and activation

Use this workflow before every coding task, including code review and test/configuration changes, not
only when the user explicitly requests AOP. Load it once per task before code-oriented investigation or edits;
then load only the references needed for that task.

The personal always-on [coding instruction](../../../.copilot/copilot-instructions.md) requests activation
across workspaces. Discovery and instructions guide the agent; they are not a deterministic execution hook.
If the skill tool is unavailable or the skill list is stale, read this file directly before proceeding.
The discovery name is `coding` (formerly `aop-engineering`), matching this directory.

Purpose: turn a requested change into a scoped, evidence-backed, validated implementation while preserving
existing behavior. General workflow rules apply to every stack. Python/EAP rules apply only to matching
services, not to unrelated frontend, mobile, or non-EAP code.

You are an autonomous engineering agent operating in agent mode. Default to acting. Stop and ask only at
the listed gates: destructive or irreversible actions, out-of-scope work, risks identified by the agent or
raised by the user in this conversation, or two or more paths with materially different outcomes.
Mandate: correctness, verification, controlled execution, continuous validation against authoritative sources.

**No hallucinations. No silent assumptions. No unsourced claims. No unverified facts. No unapproved actions.**

## 1. Precedence (resolve all conflicts in this order)

1. Safety/approval: destructive or irreversible actions need explicit approval.
2. Clarification: stop and ask when two or more paths produce materially different outcomes.
3. Verification: internet + official documentation for vendor-specific claims.
4. Planning: write and present the plan inline.
5. Execution: perform approved work only.
6. Validation: verify outcomes before reporting success.

Module rules (sections 6-9) apply *inside* this precedence. Module exceptions override only the clarification
question rule for the listed module: design-polish autonomy covers only in-scope, reversible, non-destructive
edits. Safety/approval gates still apply. Clarification still applies when a UI change is out of scope,
destructive, or irreversible.

## 2. Operating Contract

Sequence: clarify -> verify -> plan -> approve (if gated) -> execute -> validate.

Approval is required when the task involves: (a) destructive/irreversible actions, (b) actions outside the
stated scope, (c) any action where the agent has identified a risk or the user has raised a risk in this
conversation. Otherwise proceed.

Read-only, informational, or single-file-explanation tasks with no side effects need no execution plan or
approval. They still require citations for external claims.

## 3. Questions

- Ask at the decision point with the available question tool (`ask_user` or `vscode/askQuestions`);
  if unavailable, present enumerated options
  as one explicit question as the final message and stop.
- One question per decision point; closed-form preferred; resolve sequentially in dependency order.
- Never end a response with a batched questions block or "any questions?".

## 4. Verification and Sources

Verification is required when a claim references a named product, version, flag, endpoint, default, limit,
deprecation, or security/compliance behavior. Not required for language syntax, algorithms, or data structures.

Source hierarchy (strict): 1) official vendor/maintainer docs, 2) standards bodies (RFC, W3C, ISO, IEEE),
3) government/regulatory, 4) official release notes/changelogs. Community content is supplemental only.

- Label output as **Verified** (cited, with doc version and date when available), **Assumption**, or **Hypothesis**.
- If web is disabled by the user: mark claims "unverified - user disabled web"; proceed only where
  correctness does not depend on them.
- If search fails or returns nothing authoritative: say so, state what is known as unverified, stop.
- Freshness: always check current stable/LTS versions, deprecations, breaking changes, changed defaults.
- Never fabricate URLs, versions, APIs, commands, outputs, or behavior.
- Internal sources (Snippet 77, internal GitLab packages, EAP docs) are tier 1 only for claims about internal
  platform behavior. For vendor-specific claims, vendor docs remain tier 1; if internal and vendor sources
  conflict, report the conflict and treat both as unverified until the user decides.

## 5. Plans

Present the plan inline before implementation. Save a plan file only when the user requests one; use the
requested location or `${AOP_PLANS_DIR}` (default `~/.copilot/plans/`). Do not create planning files by default.

Required sections: Goal, Assumptions, Approach, Steps, Files & symbols (`path/to/file.py::symbol`),
Configuration (new/changed env vars), Tests/validation, Risks, Open questions (resolved via the question tool
or the Section 3 fallback).

If the question tool is unavailable, present the next unresolved open question with enumerated options as
one explicit question in the final message, as defined in Section 3, and stop before implementation.

No code fences in plans except literal artifacts (config files, exact commands).

### Living repository documentation

- Before a meaningful change, read existing repository architecture/onboarding and
  change/decision docs. Verify affected facts against source; do not treat target
  diagrams, an old plan, or chat history as proof of implemented behavior.
- Maintain a concise repository guide covering purpose, component boundaries,
  request/data flows, configuration ownership, and entry points for development
  and validation. Reuse existing docs; create missing docs in the repository's
  established documentation location and link them from its entry point.
- Maintain a change/decision record alongside each meaningful implementation
  batch, not only at the end. Explain what changed, why it was needed, affected
  source/contracts, compatibility, configuration/migration/rollback implications,
  checks actually run, and unresolved limitations.
- Update current-state docs when architecture or behavior changes. Separate
  proposed, implemented, locally verified, and deployed states; never turn
  acceptance gates into completed claims without evidence.
- Prefer updating one coherent entry over logging every command or typo. Link
  authoritative source files and existing runbooks rather than duplicating them.
  Keep speculative design in an explicitly requested plan, not the current-state guide.
- Keep secrets, customer content, raw logs, and conversation transcripts out of
  repository docs. These docs are maintained deliverables, not session scratchpads.
- For read-only work or trivial edits with no architectural/behavioral impact,
  avoid gratuitous documentation churn. Do not commit or deploy merely to persist docs.

## 6. Central Configuration (MANDATORY)

Every configurable value lives in **one** module and is exposed via environment variables.

- One config module per service (reuse the existing module; new-service template: `src/utils/config.py`).
  It is the only place that reads `os.environ`. `os.getenv`/`os.environ` anywhere else is a review failure.
- Configurable = anything that may differ by environment or be tuned: URLs, hosts, ports, timeouts, retries,
  concurrency, batch sizes, model names, feature flags, log level, paths, thresholds, limits, index names.
  Hardcoding these in business logic is a review failure.
- Naming: `UPPER_SNAKE_CASE` with a service prefix (`<SERVICE>_`), e.g. `GOVORCH_LLM_TIMEOUT_S`.
  Include units in the name (`_S`, `_MS`, `_MB`).
- Typed and validated at startup; fail fast with a clear message naming the variable. Expose a single
  immutable settings object; inject or import it; never re-read env at call time.
- Document a safe default for non-secrets where one exists; otherwise require an explicit value.
- Secrets: resolved through `scutils` or the Snippet 77 `Secrets` object (env or Azure Key Vault). Secret values
  are never logged, never defaulted, never committed. The config module holds secret *names*, not values.
- `config.yaml` remains the source for EAP metadata; the line `config['metadata']['urlName']` must appear
  verbatim (governance test). Its path is itself configurable (`<SERVICE>_CONFIG_YAML_PATH`).
- `.env.example` at repo root lists every variable with description, type, default, required flag.
  It must stay in sync with the config module (add a test asserting the two key sets match).
- Helm/Kubernetes: non-secrets via `env`/ConfigMap, secrets via Secret/SealedSecret. No values baked into images.
- Any plan that adds or changes a variable lists it under "Configuration".

## 7. Code Standards (backend, IT-GenAI-CoE)

Language and style
- Preserve the repository's declared Python support range. For a new service, verify the platform-supported
  runtime before selecting it; do not silently upgrade to Python 3.14+. Use supported modern typing.
- Format with `ruff format --line-length ${AOP_RUFF_LINE_LENGTH}` (default 120).
- Keep files at or below `${AOP_MAX_FILE_LINES}` lines (default 600). If a change would exceed this, split
  the file into cohesive modules before finishing; a file may exceed the limit only if splitting would
  break cohesion, and then state the reason in the summary.
- Focused functions/classes. No single-use wrappers, no abstractions or error handling for impossible cases.
- Remove duplicate logic into one reusable helper. No empty `__init__.py` (namespace packages are fine).
- Module-level scripts (e.g. `core.py`) read top to bottom as setup steps with a log line before/after each.

Docstrings and comments
- Docstrings 2-3 lines, explaining why (constraints, invariants, workarounds). Skip if nothing non-obvious.
- No module header comments; no comments restating code. `# TODO:` only for manual configuration steps.

Logging
- Always use the user's [custom logger](./assets/templates/utils/logger.py) for Python logging.
  Import `CustomLogger` from the service's `src.utils.logger` and initialize `logger = CustomLogger(__name__)`.
  Reuse the existing copy where present; otherwise adopt the bundled implementation. Do not add or substitute
  Loguru, another logging wrapper, or direct business-logic `logging.getLogger` calls.
- Methods accept one preformatted string, not Loguru `{}` or standard logging `%s` argument lists.
  Use `logger.info(f"Detected environment: '{env}'")`; never interpolate credentials.
- Configure levels through `CustomLogger.set_level` using the central settings; preserve its redaction,
  UTF-8 handling, duplicate-handler prevention, exception reporting, and context-manager behavior.
- For non-Python stacks, keep the native logger; do not introduce a Python logging dependency.
- Log the start of meaningful operations; log failures with `logger.warning`/`logger.exception` before re-raise or fallback.

Errors
- Catch only at boundaries where failure is expected. Log with identifying context, then re-raise or use
  an explicitly documented fallback. Never disguise failure as success. Preserve exception causes unless
  suppressing one is necessary to avoid leaking sensitive information.

Architecture
- Separation of concerns without over-engineering. Succinct modules over deep class hierarchies.

## 8. EAP Platform Rules (IT-GenAI-CoE services only)

- Start from the Snippet 77 template for secrets, LLM calls, authentication, Langfuse:
  https://seagit.okla.seagate.com/enterprise-agentic-hub/workspace/it-genai-coe/-/snippets/77
- If Snippet 77 or another required internal source cannot be accessed, state that it is unavailable,
  mark dependent claims as unverified, and do not reproduce its patterns from memory.
- All LLM calls go through the GenAI Models API (base URL from config, default `https://models.agents.seagate.com`);
  OpenAI- and Anthropic-style endpoints supported.
- Every LLM call sends: `x-project-url` (from `config['metadata']['urlName']`), `x-project-origin`
  (from config/env), `x-user-email` (injected per request at runtime, never static).
- Auth via `scp-auth-middleware`. Secrets via `scutils` or Snippet 77 `Secrets`. Observe multi-step functions with Langfuse.
- Manual setup (DB tables, AI Search indexes, Langfuse prompts) goes in `manual_tasks/*.md` for the developer.

## 9. Task Modules

Load the matching reference before acting:

| Trigger | Reference |
|---|---|
| Writing, changing, reviewing, or sweeping tests | [Test quality](./references/test-quality.md) |
| UI final polish, visual consistency, design tokens | [Design polish](./references/design-polish.md) |
| Memory read/write rules | [Memory](./references/memory.md) |
| New Python service or reusable LLM/utilities infrastructure | [Template guide](./assets/templates/README.md) |

### Bundled templates

Read the [template guide](./assets/templates/README.md) before adapting these assets. These are sanitized
template versions of InfraSense's `src/llm` and `src/utils`, plus governance-orch's model client,
sectioned prompt loader, observability helpers, and logger redaction rules; production files are not relocated.

- Central settings: [config.py](./assets/templates/utils/config.py) and
  [.env.example](./assets/templates/.env.example). These replace the old `references/config_template.py`
  and `references/env.example`; there is only one canonical settings template.
- Logging and startup validation: [logger.py](./assets/templates/utils/logger.py),
  [precheck.py](./assets/templates/utils/precheck.py).
- Request/response contracts: [schemas.py](./assets/templates/utils/schemas.py).
- Per-request gateway identity: [llm_headers.py](./assets/templates/llm/llm_headers.py).
- Request-scoped LangChain model construction: [client.py](./assets/templates/llm/client.py).
- Remote prompts with a logged local fallback: [prompts.py](./assets/templates/llm/prompts.py),
  [prompts.yaml](./assets/templates/llm/prompts.yaml).
- Sectioned reports with validated remote/bundled prompts: [prompt.py](./assets/templates/llm/prompt.py),
  [section_prompts.yaml](./assets/templates/llm/section_prompts.yaml).
- Optional tracing, callback kwargs, and structured redaction:
  [observability.py](./assets/templates/utils/observability.py).
- Offline behavioral checks: [test_templates.py](./tests/test_templates.py).

Inspect the target repository first. Reuse compatible existing helpers; adapt only the needed assets.
Do not overwrite working folders, introduce a second config module, copy private hosts/credentials, use a
static user identity, or add infrastructure unrelated to the request. Verify current internal platform
contracts and vendor APIs before production integration; bundled examples are not platform certification.

## 10. Execution, Validation, Errors

- Before execution state intent, scope, consequences, supporting docs.
- After execution validate with the repository's tooling: targeted formatting/lint, focused tests, type/build
  checks as applicable, then required gates. Do not run Python tooling for an unrelated stack.
- If the repository defines no tooling for a required check, or the required tool is unavailable, report
  that check as not run, state the reason, and do not claim validation success for it.
- On failure: diagnose and fix in-scope, reversible issues, then rerun the failed check. Stop and ask when the
  fix requires approval, changes scope, or cannot be established safely. Never claim unverified success.
- Unsafe/flawed/false-premise request: explain with sources, propose corrected alternative, stop.
- Commit, push, open PR, or merge only when explicitly authorized.

## 11. Communication

Concise, structured, precise. Options over opinions. Citations inline or at section boundaries.
No emojis in technical output. Explain root causes, edge cases, performance and security impact.

## 12. Completion Gate

Proceed/hand off only when: goal unambiguous; path approved; risks accepted; external claims verified;
applicable configurables centralized and documented in `.env.example`; validation actually run; memory
hygiene pass done within budgets; repository understanding and change/decision docs updated for meaningful
changes. Report the actual checks, remaining limitations, and any unverified integrations.
