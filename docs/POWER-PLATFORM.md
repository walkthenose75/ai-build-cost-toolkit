# Using the toolkit in a Power Platform project

The toolkit is a developer tool installed beside or into the Python environment
for the project being measured. Do not add the entire toolkit as a Git
submodule. The project's source repository receives only its own `.aic` state,
approved reports, and—when applicable—the generated Code App page.

## Install from GitHub

Create a project-local tools environment and install the toolkit. The
repository is public, so no GitHub authentication is required; if your fork is
private, run `gh auth setup-git` first.

```powershell
cd C:\VSCodeProjects\my-power-platform-project
py -m venv .aic-tools
.\.aic-tools\Scripts\Activate.ps1
python -m pip install "git+https://github.com/walkthenose75/ai-build-cost-toolkit.git"
python -m ai_build_cost doctor
```

Add `.aic-tools/` and `.aic/` to the consuming project's `.gitignore`. Commit
only approved rate cards, immutable baselines, generated page files, and
shareable reports.

## New project

Start tracking when development begins:

```powershell
python -m ai_build_cost checkpoint --repo . --dir .aic --label "project started"
```

At the first release, preserve the immutable baseline:

```powershell
New-Item -ItemType Directory -Path reports -Force
Copy-Item .aic\aic-report.json reports\initial-build.json
```

Future checkpoints remain cumulative. The dashboard and Code App page derive
maintenance as current minus that baseline.

## Existing project

If prior work used GitHub Copilot CLI from the same repository directory, the
first checkpoint collects those matching sessions:

```powershell
python -m ai_build_cost checkpoint --repo . --dir .aic --match cwd --label "historical baseline"
```

If the repository moved or was recloned, use `--match both` so repository
identity can supplement the working-directory match. To begin reporting from a
specific date instead of using all available CLI telemetry, add an ISO timestamp:

```powershell
python -m ai_build_cost checkpoint --repo . --dir .aic --match both --since 2026-08-01T00:00:00Z --label "tracking adopted"
```

Keep that filter unchanged for later checkpoints. VS Code Copilot Chat sessions
are not recoverable because its store does not expose usage telemetry.

## Add the page to a Power Apps Code App

Generate a current checkpoint, then install the component and typed data module:

```powershell
python -m ai_build_cost checkpoint --repo . --dir .aic --label "before release"
python -m ai_build_cost install-code-app-page `
  --report .aic\aic-report.json `
  --target src\features\ai-build-cost
```

When an immutable baseline exists:

```powershell
python -m ai_build_cost install-code-app-page `
  --report .aic\aic-report.json `
  --baseline reports\initial-build.json `
  --target src\features\ai-build-cost `
  --force
```

The target contains:

- `AiBuildCostPage.tsx` — reusable React page and report types;
- `AiBuildCostPage.css` — scoped responsive styling;
- `aic-data.ts` — typed current and optional baseline reports;
- `index.ts` — public exports;
- `README.md` — wiring example.

The component never accesses the developer's local session database. It renders
the generated data committed or copied into the app.

### Copilot Chat prompt to wire the page

```text
Wire src/features/ai-build-cost into this Power Apps Code App using the
project's existing page union, page switch, and navigation conventions. Render
AiBuildCostPage with AIC_CURRENT_REPORT and AIC_BASELINE_REPORT. Keep the
component presentational, do not change the AIC calculations or evidence
classifications, and run the project's existing TypeScript/build validation.
```

## Other Power Platform solution types

| Project type | Recommended integration |
|---|---|
| Power Pages | Generate the self-contained HTML report and host it in an approved location, or consume `aic-report.json` in a site-specific component. |
| Canvas app | Publish the HTML report behind an approved URL and link to it; Canvas cannot read the local SQLite store. |
| Model-Driven app | Link the hosted report from navigation or embed an approved web resource/custom page. |
| PCF control | Keep collection in the control repository and consume the report JSON in a purpose-built control only when an in-app view is required. |
| Power Automate | Track the flow source repository and publish the HTML/JSON report as release evidence; the flow runtime does not collect Copilot CLI telemetry. |
| Mixed solution | Run one stable ledger per repository, or use separate ledger directories when collection scopes differ. |

## Refresh prompt

After a meaningful feature or release:

```text
Use the aic-tracker workflow for this repository. Refresh the cumulative
checkpoint with the existing .aic scope and rate card, validate the report,
update the installed Code App page data with install-code-app-page --force,
regenerate the shareable HTML dashboard, and report measured versus modeled
values without presenting compute valuation as an invoice.
```
