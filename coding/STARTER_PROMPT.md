# Starter prompt (paste into a new chat / agent session)

Load the `coding` skill ([SKILL.md](./SKILL.md) plus the reference matching the task) before coding.
The personal always-on instruction already requests this; this prompt is an optional explicit task brief,
not a prerequisite for activation. If discovery is stale, read SKILL.md directly.

Task: <describe the change>
Repo/service: <path or name>   Service env prefix: <PREFIX_>
Scope limits: <files/dirs in scope; anything off-limits>
Web access: allowed | disabled
Authorized actions: read-only | edit files | run tests | commit | open PR

Do, in order:
1. Inspect the repo: stack, versions, existing config module, `.env.example`, AGENTS.md, CI gates. Record
   confirmed environment facts to memory.
2. Inspect configuration in the affected scope; flag `os.getenv`/`os.environ` reads outside the central config.
   Do not turn a focused request into an unrelated repository-wide migration.
3. Verify any vendor/version-specific behavior against official docs; label Verified / Assumption / Hypothesis.
4. If more than one materially different path exists, ask one closed-form question and stop.
5. Present the plan inline, including a "Configuration" section (new/changed env vars).
   Save a plan file only if requested.
6. Execute only within authorized actions. Centralize configuration per SKILL.md section 6; keep
   `config['metadata']['urlName']` verbatim; route LLM calls through the Models API with the three headers.
7. For new LLM/utilities scaffolding, read the [template guide](./assets/templates/README.md) and adapt only
   missing components. Do not overwrite existing helpers or change the supported runtime.
8. Validate using the repo's tools: formatting/lint, focused tests (apply the test-quality authoring gate),
   type/build checks, and `.env.example` sync for configuration changes. Apply EAP rules only to EAP services.
   Report actual commands run and results; never claim unverified success.
