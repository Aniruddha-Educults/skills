# Design Polish (final quality pass before shipping)

Scope: `$ARGUMENTS` (specific components/pages) or full UI. Autonomous for in-scope, reversible styling fixes;
infer intent from the existing design language. Anything requiring a design decision, new assets, or touching
behavior goes to "Remaining items", not executed.

Verify modern CSS features (container queries, `text-wrap`, `oklch`, `color-mix`, `light-dark()`,
scroll-driven animations) against MDN / caniuse for the project's browser targets before introducing them.

## Phases
1. **Discovery**: stack, UI framework, CSS approach, component library. Catalog spacing, colors, typography,
   radius, shadows, motion; most-used value = canonical. Flag and rank deviations.
2. **Spacing/alignment**: snap to scale; consistent gap vs margin; baselines, icon-text centering, form and
   list alignment; consistent container padding and max-width; `clamp()` for fluid spacing.
3. **Typography**: consistent h1-h6/body/caption; ~75ch line length; `text-wrap: balance|pretty`; consolidate
   weights; 0.05-0.1em tracking on uppercase; body >= 14px; fluid sizes via `clamp()`.
4. **Color/contrast**: single primary value; semantic colors not swapped; one gray temperature; WCAG AA
   4.5:1 for text and placeholders; visible focus rings; distinguishable disabled state.
5. **Interactive states**: hover on all clickables without layout shift; `:focus-visible` outline with offset;
   pressed state; touch targets >= 44x44 (48 preferred); disabled = muted + `not-allowed`, no hover.
6. **Motion**: 100-150ms micro, 200-300ms state, 300-500ms page; standard easing, no linear except progress;
   50-100ms stagger; honor `prefers-reduced-motion`.
7. **Mobile**: Flutter (theme EdgeInsets/textTheme, SafeArea, keyboard insets), SwiftUI (spacing scale, Dynamic
   Type, safe areas), Compose (theme spacing/typography, WindowInsets).
8. **Micro-details**: 1px gaps, stretched images, silent clipping, icon sizes, leftover placeholder text,
   consistent button verbs, helpful empty states, error formatting, dark-mode shadows/borders/overlays.

## Tokens and configuration
Design values belong in one token source (CSS custom properties / theme file). Runtime-configurable UI
values (API base URL, feature flags, theme defaults) come from the central config via env vars at build/runtime,
never hardcoded in components.

## Apply
Group by file; order spacing -> typography -> color -> motion; minimal diffs; preserve conventions.
Classify: Critical (apply), Improvement (apply), Enhancement (apply only if no regression risk).

## Validate
Build; correct or undo only your own failing edits, preserving pre-existing user changes; no new lint warnings;
run visual regression (Storybook/Chromatic/
Percy/golden) if configured; run a11y linters; re-check focus and contrast.

## Report
Summary table (Category | Found | Fixed | Skipped) for Spacing, Alignment, Typography, Color, Motion,
Hover/Focus, Mobile, Micro-details, Total. Files modified (one line each). Top 3 before/after.
Remaining items. Self-evolution notes (hot categories, missing tokens, follow-ups).
