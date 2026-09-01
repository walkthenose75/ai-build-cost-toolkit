---
name: aic-tracker
description: "Measure AI consumption for GitHub Copilot CLI projects: tokens, prompt-cache reuse, modeled compute cost, telemetry-recorded premium credits, active generation time, cumulative checkpoints, and a shareable AI Build Cost dashboard. Triggers: AIC, AI cost, build cost, token usage, credits used, running total, AI consumption dashboard."
---

# AIC Tracker

Use `python -m ai_build_cost` to produce evidence-safe AI build-cost reports.
If the module is unavailable, install the toolkit from
`https://github.com/walkthenose75/ai-build-cost-toolkit`.

## Rules

1. Run `python -m ai_build_cost doctor` before the first collection.
2. Use the repository root as `--repo` and one stable, project-specific
   `--dir` for all cumulative checkpoints.
3. Verify and date the project's pricing file. Token cost is modeled and is
   never described as an invoice.
4. Use telemetry-recorded premium credits when available. Never fabricate
   credits from a stale multiplier table.
5. Disclose every default- and prefix-rated model.
6. Keep measured, modeled, estimated, and unavailable evidence separate.
7. Never upload or commit `~/.copilot/session-store.db`.

## Standard checkpoint

```text
python -m ai_build_cost checkpoint --repo <repo> --dir <repo>/.aic --pricing <repo>/.aic/pricing.json --label "<milestone>"
```

Then validate and publish:

```text
python -m ai_build_cost validate --report <repo>/.aic/aic-report.json
python -m ai_build_cost dashboard --report <repo>/.aic/aic-report.json --ledger <repo>/.aic/aic-ledger.csv --title "<project> - AI Build Cost" --output <repo>/reports/ai-build-cost.html
```

If the project has an immutable initial-build report, add:

```text
--baseline <repo>/reports/initial-build.json
```

The dashboard derives Since Baseline as current minus initial. Never sum
cumulative checkpoints.

## Report to the user

Lead with cumulative modeled compute, credits or their unavailable state, total
input/output, cache-read share, active generation time, and the delta since the
previous checkpoint. Name default- and prefix-rated models and repeat that compute cost
is a rate-card valuation, not an invoice.

## Data availability

The local collector reads GitHub Copilot CLI's
`~/.copilot/session-store.db` tables `sessions` and
`assistant_usage_events`. VS Code Copilot Chat does not expose this table, so
those sessions cannot be recovered by this workflow.
