# Test Quality

Two modes, one value bar. Optimize for confidence, not deletion count.

## Authoring gate (every new/changed test)
Answer all four or do not add the test:
1. What observable behavior, invariant, or independent contract does it protect?
2. What credible regression makes it fail?
3. Why does existing coverage not catch it? Prefer extending a table-driven case or shared fixture.
4. Does it need a production seam no production caller needs? If yes, test at the real boundary instead.

- A test that breaks under behavior-preserving refactoring asserts implementation; rewrite it at the owning boundary.
- Bug regression tests must fail on pre-fix code for the intended reason and pass after the fix.
- Config: tests override settings by setting env vars / constructing the settings object, never by patching
  hardcoded values. Include one test asserting `.env.example` keys match the config module.

## Value and retention bar
Keep tests that enforce a public API, SDK, protocol, config, migration, storage, security, platform, default,
prompt-byte, cross-language, package, release, or architecture contract; observable call ordering; credible
regressions; cheapest-independent-guard source inspection. Static or slow is not a deletion reason.

Before judging: read the full test, production owner, entry point, callers, callees, siblings, overlapping
tests, CI routing, history, and AGENTS.md files.

## Audit discovery (read-only, report before editing)
Lanes: core/packages, plugins, UI/apps/scripts/tooling, cross-cutting sweep. Look for assertion-free probes,
self-comparisons, copied fixtures/manifests, exact source greps, private-predicate tests duplicated at real
boundaries, duplicate invocations, replays of shared helpers, tests preserving test-only exports, dead code
whose only callers are tests.

## Candidate evidence (all required before deletion)
Test name/location; detectable failure; non-test callers; stronger remaining proof; history/reason;
deletion unlocked; risk + focused validation command.

## Edit shape
One coherent owner-boundary batch per PR. Delete obsolete test-only seams instead of aliasing. Prefer
net-negative production LOC. No replacement tests restating implementation.

## Validation
Never edit while a test runner is active. Run smallest owner + sibling tests, targeted formatting, diff check,
changed-file policy gates, diff stat (production vs test LOC), standard review pass.

## Landing and handoff
Commit/push/PR/land only when authorized (precedence rule 1). Report: root cause, removed categories,
production simplifications, retained false positives and why, proof run, production vs test LOC, PR state, follow-ups.
