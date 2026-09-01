# Project integration

## Recommended repository layout

```text
.aic/
  pricing.json          # reviewed project rate card
  aic-state.json        # latest cumulative baseline for delta calculation
  aic-ledger.csv        # append-only checkpoint history
  aic-report.json       # latest priced cumulative report
reports/
  initial-build.json    # immutable release baseline
  ai-build-cost.html    # shareable dashboard
```

Choose whether `.aic` belongs in source control. A good default is:

- commit the reviewed pricing file, release baselines, dashboard, and dated
  checkpoint exports;
- ignore mutable local state;
- never commit the Copilot SQLite database.

## Release checklist

1. Run the project tests and build.
2. Verify and date the rate card.
3. Run `aic checkpoint` with the same project scope and ledger directory.
4. Investigate every fallback-rated model.
5. Investigate every prefix-rated model and replace it with an exact key or
   explicit alias when possible.
6. Run `aic validate`.
7. Generate the dashboard.
8. Review repository name, dates, and aggregate model usage before sharing.
9. Commit the report with the product change or release evidence.

## Cloud-export interoperability

The calculator accepts either a legacy array of model rows or this envelope:

```json
{
  "schemaVersion": 1,
  "generatedAt": "2026-08-31T20:00:00Z",
  "scope": {
    "repository": "owner/repository",
    "sessionCount": 3
  },
  "totals": {
    "premium_credits": 12.5
  },
  "models": [
    {
      "model": "example-model",
      "input_tokens": 100000,
      "output_tokens": 5000,
      "cache_read_tokens": 80000,
      "cache_write_tokens": 10000,
      "reasoning_tokens": 0,
      "active_ms": 30000,
      "requests": 4
    }
  ]
}
```

This allows an agent with authorized cloud session-store access to export
aggregate data without changing the calculator or dashboard.

## Embedding in an application

Prefer consuming `aic-report.json` rather than copying dashboard logic. The JSON
contract is intentionally presentation-neutral. A React, Power Apps Code App,
or static site can map `totals`, `models`, `evidence`, and `rateCard` into its
own design system.

For lifecycle views, persist an immutable initial report and derive maintenance
as `current - initial`. Never sum checkpoint snapshots; every snapshot is
cumulative.

For Power Apps Code Apps, prefer the packaged `install-code-app-page` command
over copying the standalone dashboard implementation. It generates a typed
`aic-data.ts` module and installs a React component that consumes the same
validated report contract. See [Power Platform integration](POWER-PLATFORM.md).
