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
2. Use one stable project-specific ledger directory.
3. Verify and date the project's pricing file. Cost is modeled, not an invoice.
4. Use telemetry-recorded premium credits; never invent missing credits.
5. Disclose default and prefix-rated models.
6. Keep measured, modeled, estimated, and unavailable evidence separate.
7. Never upload or commit `~/.copilot/session-store.db`.

## Workflow

Run a checkpoint:

```text
python -m ai_build_cost checkpoint --repo <repo> --dir <repo>/.aic --pricing <repo>/.aic/pricing.json --label "<milestone>"
```

Validate and generate the report:

```text
python -m ai_build_cost validate --report <repo>/.aic/aic-report.json
python -m ai_build_cost dashboard --report <repo>/.aic/aic-report.json --ledger <repo>/.aic/aic-ledger.csv --title "<project> - AI Build Cost" --output <repo>/reports/ai-build-cost.html
```

Add `--baseline <repo>/reports/initial-build.json` when an immutable initial
report exists. The dashboard derives the increment as current minus baseline;
never sum cumulative checkpoints.

## User report

Lead with modeled compute, credits or their unavailable state, input/output
tokens, cache-read share, active generation, and delta since the previous
checkpoint. Name every default- or prefix-rated model and repeat that compute
cost is a rate-card valuation, not an invoice.

The collector reads GitHub Copilot CLI's local `sessions` and
`assistant_usage_events` tables. VS Code Copilot Chat sessions cannot be
recovered by this workflow.
