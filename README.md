# AI Build Cost Toolkit

Turn local GitHub Copilot CLI telemetry into an auditable, cache-aware AI
consumption report and a shareable, self-contained dashboard.

The toolkit deliberately separates four kinds of evidence:

| Classification | Included evidence |
|---|---|
| **Measured** | Token buckets, model names, request counts, active generation time, telemetry-recorded request multipliers |
| **Modeled** | API-equivalent compute value from an editable, dated rate card |
| **Estimated** | Optional labor, alternative-build, or maintenance assumptions supplied by your project |
| **Unavailable** | Anything not present in telemetry or a separately documented source |

> The dollar figure is a rate-card valuation, **not a GitHub Copilot invoice**.
> Premium-request or AI-credit policies change over time. The toolkit uses the
> `request_multiplier` recorded in telemetry when available and reports
> unavailable rather than inventing a value.

## What you get

- A dependency-free Python CLI (`aic`) for Windows, macOS, and Linux.
- Project-scoped collection from `~/.copilot/session-store.db`.
- Correct prompt-cache accounting: fresh input, cache reads, cache writes, output.
- A cumulative checkpoint ledger with regression protection.
- Scope/rate-card identity checks and an interprocess lock for audit-safe deltas.
- Explicit fallback-rate disclosure for unknown models.
- Explicit review flags for coarse prefix matches; exact aliases are configurable.
- A responsive, accessible, dark-mode-aware single-file HTML dashboard.
- A drop-in React/TypeScript report page for Power Apps Code Apps.
- An installable GitHub Copilot CLI skill for repeatable agent-driven refreshes.
- Unit tests, CI, sample data, methodology, privacy guidance, and migration notes.

## Before you start

This tool reads **local** GitHub Copilot **CLI** telemetry
(`~/.copilot/session-store.db`) on the machine where you work. Confirm all three
before your first run:

- **Python 3.9+** is installed.
- You built or worked on the project you want to measure using the **Copilot
  CLI** (the terminal agent). VS Code Copilot **Chat** is not recorded and
  cannot be measured.
- You are measuring a project **on this machine** — telemetry is local and is
  never uploaded.

Run `python -m ai_build_cost doctor` first to confirm the store exists and is
supported. Token, credit, and active-time values are measured directly; the
**dollar** value uses an *example* rate card, so verify and date `pricing.json`
before quoting any dollar figure.

## Install

Requires Python 3.9+ and usage recorded by **GitHub Copilot CLI**.

```powershell
git clone https://github.com/walkthenose75/ai-build-cost-toolkit.git
cd ai-build-cost-toolkit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m ai_build_cost doctor
```

VS Code Copilot Chat uses a different store and does not expose the
`assistant_usage_events` telemetry table used here. Those sessions cannot be
reconstructed by this tool.

## Five-minute workflow

From the project you want to measure:

```powershell
python -m ai_build_cost checkpoint `
  --repo . `
  --dir .aic `
  --label "release candidate"

python -m ai_build_cost dashboard `
  --report .aic\aic-report.json `
  --ledger .aic\aic-ledger.csv `
  --title "My Project — AI Build Cost" `
  --output reports\ai-build-cost.html
```

Open `reports\ai-build-cost.html` in any browser. It has no server or runtime
dependency and can be shared after you review the embedded project metadata.

### Baseline and maintenance views

Preserve the report from the initial build, then compare it with the latest
cumulative report:

```powershell
Copy-Item .aic\aic-report.json reports\initial-build.json

# Later, after more work:
python -m ai_build_cost checkpoint --repo . --dir .aic --label "feature 2 complete"
python -m ai_build_cost dashboard `
  --report .aic\aic-report.json `
  --baseline reports\initial-build.json `
  --ledger .aic\aic-ledger.csv `
  --output reports\ai-build-cost.html
```

The dashboard then provides **Initial**, **Since baseline**, and **Combined**
views. Since-baseline values are always derived as `current cumulative -
baseline`; checkpoint rows are an audit trail and are never summed.

Changing the collection filter, repository identity, session scope, or rate
card requires `--allow-scope-change` or `--reset`. The prior state and ledger
are timestamp-archived before a new baseline starts.

## Commands

| Command | Purpose |
|---|---|
| `aic doctor` | Verify the local Copilot store and required tables. |
| `aic collect` | Export a project- or session-scoped raw telemetry snapshot. |
| `aic calculate` | Apply cache-aware pricing to an existing snapshot. |
| `aic checkpoint` | Collect, calculate, append the ledger, and save the latest report. |
| `aic dashboard` | Generate a self-contained HTML dashboard. |
| `aic validate` | Validate the required report shape and non-negative counters. |
| `aic install-code-app-page` | Install a typed report page and generated data into a Power Apps Code App. |

Use `python -m ai_build_cost <command> --help` for all options. The shorter
`aic` command is also installed and works automatically inside an activated
virtual environment or when the Python scripts directory is on `PATH`.

## Rate cards

`ai_build_cost/pricing.json` is an **example**, not a promise of current prices.
Copy it into your project, verify every rate against the provider or your
contract, update `version`, and pass it explicitly:

```powershell
Copy-Item .\ai_build_cost\pricing.json .\.aic\pricing.json
python -m ai_build_cost checkpoint --repo . --dir .aic --pricing .aic\pricing.json --label "validated rates"
```

Model names prefer exact keys, then explicit `aliases`, then a longest-prefix
continuity match. Prefix matches are listed under
`rateCard.prefixRatedModels` for review. Unknown models use `models.default`
and are listed under `rateCard.fallbackRatedModels`.

## Install the Copilot skill

```powershell
python -m ai_build_cost install-skill
```

The command works across operating systems and copies the single packaged
skill (`ai_build_cost/skill/SKILL.md`) to your personal Copilot skills
directory. `scripts\install-skill.ps1` is a Windows convenience wrapper for
source checkouts that installs that same file.

## Add it to a Power Platform project

The toolkit is installed as a developer tool; it is not added as a Git
submodule. From the project being measured:

```powershell
python -m ai_build_cost checkpoint --repo . --dir .aic --label "initial checkpoint"
python -m ai_build_cost install-code-app-page `
  --report .aic\aic-report.json `
  --target src\features\ai-build-cost
```

See [Power Platform integration](docs/POWER-PLATFORM.md) for new-project,
existing-project, baseline, Code App wiring, and Copilot Chat instructions.

## Security and privacy

The raw Copilot SQLite store can contain session metadata. The toolkit reads it
locally and never uploads it. Derived reports include repository identity, aggregate telemetry, model names,
timestamps, and whether collection was project- or single-session scoped, but
not prompts, responses, session summaries, or raw session IDs. Review reports
before sharing.

See [Methodology](docs/METHODOLOGY.md),
[Project integration](docs/PROJECT-INTEGRATION.md), and
[Review findings](docs/REVIEW-FINDINGS.md).

The toolkit also dogfoods itself: see the measured
[v1 build report](reports/toolkit-build-cost.html) and its
[JSON source](reports/toolkit-build-cost.json).

## Development

```powershell
python -m unittest discover -s tests -v
python -m ai_build_cost doctor
```

Licensed under the [MIT License](LICENSE).
