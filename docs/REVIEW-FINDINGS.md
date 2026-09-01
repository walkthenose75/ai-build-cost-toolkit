# Review findings and improvements

This toolkit was extracted after reviewing an earlier single-script AIC skill
and an application-specific AI Build Cost page.

| Finding | Risk | Improvement in this repository |
|---|---|---|
| The how-to guide referenced an obsolete `events` schema while the skill referenced `assistant_usage_events`. | Collection fails or produces incomparable snapshots. | One collector owns the current local SQLite schema; `aic doctor` fails early on unsupported stores. |
| Credit estimates were derived from rate-card multipliers even when telemetry contained the actual request multiplier. | Historical billing policy changes silently rewrite results. | Credits use telemetry by distinct session/turn and remain unavailable when absent. |
| A single calculator script mixed input normalization, pricing, state, console output, and export. | Hard to test, extend, or reuse. | Collector, calculation, ledger, CLI, and dashboard are separate modules with unit tests. |
| The default ledger lived beside the skill. | Different projects could corrupt each other's delta baseline. | `checkpoint` defaults to project-local `.aic` and rejects cumulative regressions. |
| The report page contained application-specific labor assumptions, low-code comparisons, Git baselines, and inline styling. | Copying the page would copy unsupported claims and tight coupling. | The dashboard is project-neutral, consumes a documented JSON contract, and keeps labor/value outside measured telemetry. |
| Unknown models silently depended on a generic default. | The total looked more precise than the evidence. | Fallback-rated models are disclosed in JSON, console output, and the dashboard. |
| Coarse family-prefix matches could look exact and mis-price size-qualified variants. | Modeled cost can be materially overstated without warning. | Exact keys and aliases are preferred; prefix matches are separately disclosed for review. |
| Initial, maintenance, and combined views were maintained in application code. | Checkpoints could be double-counted or baselines overwritten. | The reusable dashboard accepts an immutable baseline and derives the increment arithmetically. |
| Raw store access and shareable output boundaries were not explicit. | Accidental sharing of session metadata. | The collector exports aggregates only; privacy guidance explicitly prohibits sharing the raw database. |
