# Methodology

## Evidence contract

Every number should be labeled as **measured**, **modeled**, **estimated**, or
**unavailable**. Do not combine those categories into a headline without
showing the components.

### Measured

GitHub Copilot CLI records per-request telemetry in the local SQLite table
`assistant_usage_events`:

- total input tokens;
- output tokens;
- prompt-cache read and write tokens;
- reasoning tokens when supplied;
- model generation duration;
- model identifier;
- request multiplier when supplied.

The collector matches sessions by repository working directory and aggregates
only numeric telemetry. It does not read prompt or response content.

### Modeled

Compute valuation is:

```text
fresh input = max(0, input - cache read - cache write)

cost = fresh input × input rate
     + cache read × cache-read rate
     + cache write × cache-write rate
     + output × output rate
```

Each product is divided by one million because rates are stored per 1M tokens.
The rate card must be dated and independently verified before publishing.

### Premium requests or AI credits

The toolkit sums the maximum non-null `request_multiplier` recorded for each
distinct `(session, agent, turn)` tuple. Including the agent identifier prevents
sub-agent turn indexes from colliding with the parent session. Taking the
maximum avoids double-counting retries or multiple usage rows within one turn.
The total is emitted only when every distinct request tuple has a multiplier.
If any turn is missing one, credits remain unavailable and the scope reports
known-versus-total request coverage. The pricing file is not used to fabricate
credits.

### Time

Active generation is the sum of `duration_ms`. It is model response time, not
developer labor and not wall-clock project duration. Parallel model calls can
make summed active time exceed elapsed wall time.

## Cumulative checkpoints

The ledger expects a stable project scope and cumulative snapshots. Each new
snapshot is subtracted from the previous state to create a delta. A negative
counter raises an error because it normally means the project scope, time
window, session filter, or rate card changed.

Use `--allow-scope-change` or `--reset` when intentionally changing scope.
Both archive the old state and ledger with a UTC timestamp before starting a
new baseline; the new ledger records a scope-reset marker.

Each checkpoint persists a canonical identity containing repository, collection
filter, session-scope fingerprint, rate-card version, and rate-card content
fingerprint. Changes are rejected even when every numeric counter increases.
Ledger and state updates are protected by an interprocess file lock; the ledger
is also the recovery source if a process stops before state is updated. A small
write-ahead journal lets the next checkpoint, validation, or dashboard command
finish an interrupted ledger/state/report publication without duplicating the
checkpoint.

## Known limitations

- Only locally indexed GitHub Copilot CLI telemetry is available to the Python
  collector. Cloud-only history must be exported by an authorized agent/tool
  into the same snapshot schema.
- Public API-equivalent pricing is not Copilot subscription billing.
- Model aliases are not normalized automatically; add explicit rate-card
  aliases when providers rename models.
- Exact and explicit-alias rate matches are strongest. Coarse prefix matches are
  allowed for continuity but are disclosed for review; default matches are
  disclosed as fallbacks.
- Source-code volume, Git churn, labor, value delivered, licensing, hosting,
  governance, and human review are outside the telemetry contract.
- A cache-write rate may be identical to input for providers without a distinct
  write price. Verify the semantics for every provider.
