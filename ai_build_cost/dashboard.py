from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any, Optional


def _ledger_rows(path: Optional[Path]) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-20:]


def render_dashboard(
    report: dict[str, Any],
    output: Path,
    baseline: Optional[dict[str, Any]] = None,
    ledger_path: Optional[Path] = None,
    title: str = "AI Build Cost",
) -> None:
    payload = {
        "current": report,
        "baseline": baseline,
        "ledger": _ledger_rows(ledger_path),
        "title": title,
    }
    safe_payload = (
        json.dumps(payload, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    document = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>__TITLE__</title>
  <script>
    (() => {
      const param = new URLSearchParams(window.location.search).get("scoutTheme");
      const theme =
        param || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      document.documentElement.setAttribute("data-theme", theme);
    })();
  </script>
  <style>
    :root {
      color-scheme: light;
      --cp-bg: #f7f4ef;
      --cp-bg-elevated: #fcfbf8;
      --cp-surface: #ffffff;
      --cp-surface-soft: #f5f5f5;
      --cp-border: #dedede;
      --cp-border-strong: #919191;
      --cp-text: #242424;
      --cp-text-muted: #5c5c5c;
      --cp-text-soft: #6f6f6f;
      --cp-accent: #b11f4b;
      --cp-accent-hover: #9a1a41;
      --cp-accent-soft: rgba(177, 31, 75, 0.08);
      --cp-accent-fg: #ffffff;
      --cp-success: #16a34a;
      --cp-danger: #dc2626;
      --cp-warning: #f59e0b;
      --cp-link: #0078d4;
      --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
      --cp-overlay: rgba(255, 255, 255, 0.8);
      --cp-panel: rgba(255, 255, 255, 0.86);
      --cp-panel-strong: rgba(255, 255, 255, 0.96);
      --cp-sheen: rgba(255, 255, 255, 0.55);
      --cp-highlight: rgba(177, 31, 75, 0.12);
    }
    html[data-theme="dark"] {
      color-scheme: dark;
      --cp-bg: #3d3b3a;
      --cp-bg-elevated: #343231;
      --cp-surface: #292929;
      --cp-surface-soft: #2e2e2e;
      --cp-border: #474747;
      --cp-border-strong: #5f5f5f;
      --cp-text: #dedede;
      --cp-text-muted: #919191;
      --cp-text-soft: #b0b0b0;
      --cp-accent: #fd8ea1;
      --cp-accent-hover: #fb7b91;
      --cp-accent-soft: rgba(253, 142, 161, 0.14);
      --cp-accent-fg: #1a1a1a;
      --cp-success: #4ade80;
      --cp-danger: #f87171;
      --cp-warning: #fbbf24;
      --cp-link: #4da6ff;
      --cp-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
      --cp-overlay: rgba(41, 41, 41, 0.88);
      --cp-panel: rgba(41, 41, 41, 0.72);
      --cp-panel-strong: rgba(41, 41, 41, 0.96);
      --cp-sheen: rgba(255, 255, 255, 0.04);
      --cp-highlight: rgba(253, 142, 161, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--cp-bg);
      color: var(--cp-text);
      font-family: "Segoe UI", Aptos, Calibri, -apple-system, BlinkMacSystemFont, sans-serif;
    }
    button, select { font: inherit; }
    code { font-family: Consolas, "Courier New", Courier, monospace; }
    main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0 64px; }
    header { display: grid; gap: 12px; margin-bottom: 24px; }
    h1 { margin: 0; font-size: clamp(2rem, 6vw, 3.5rem); line-height: 1; letter-spacing: -0.04em; }
    h2 { margin: 0; font-size: 1.15rem; }
    p { line-height: 1.55; }
    .eyebrow { color: var(--cp-accent); font-size: .78rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
    .subtitle, .meta { margin: 0; color: var(--cp-text-muted); }
    .meta { font-size: .86rem; }
    .notice {
      padding: 12px 16px;
      border: 1px solid var(--cp-warning);
      border-left: 5px solid var(--cp-warning);
      border-radius: .625rem;
      background: var(--cp-surface);
    }
    .notice strong { color: var(--cp-warning); }
    .periods {
      display: inline-grid;
      grid-auto-flow: column;
      gap: 4px;
      width: fit-content;
      padding: 4px;
      border: 1px solid var(--cp-border);
      border-radius: .625rem;
      background: var(--cp-surface-soft);
    }
    .periods button {
      border: 0;
      border-radius: .625rem;
      padding: 10px 16px;
      background: transparent;
      color: var(--cp-text-muted);
      cursor: pointer;
    }
    .periods button[aria-pressed="true"] { background: var(--cp-accent); color: var(--cp-accent-fg); }
    .periods button:focus-visible { outline: 3px solid var(--cp-accent); outline-offset: 2px; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 16px; }
    .card {
      min-width: 0;
      padding: 20px;
      border: 1px solid var(--cp-border);
      border-radius: 16px;
      background: var(--cp-surface);
      box-shadow: 0 0 2px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.14);
    }
    .kpi-label { color: var(--cp-text-muted); font-size: .76rem; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
    .kpi-value { margin: 8px 0 4px; color: var(--cp-accent); font-size: clamp(1.55rem, 4vw, 2.3rem); font-weight: 800; line-height: 1; }
    .kpi-detail { color: var(--cp-text-muted); font-size: .82rem; }
    section { margin-top: 20px; }
    .section-head { display: flex; align-items: start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
    .badge { padding: 4px 9px; border-radius: 999px; background: var(--cp-accent-soft); color: var(--cp-accent); font-size: .72rem; font-weight: 800; text-transform: uppercase; }
    .token-bar { display: flex; height: 18px; overflow: hidden; border-radius: 999px; background: var(--cp-surface-soft); }
    .token-bar span { min-width: 2px; }
    .fresh { background: var(--cp-accent); }
    .read { background: var(--cp-success); }
    .write { background: var(--cp-warning); }
    .output { background: var(--cp-link); }
    .legend { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; color: var(--cp-text-muted); font-size: .82rem; }
    .legend i { display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 2px; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; min-width: 760px; border-collapse: collapse; }
    th, td { padding: 11px 8px; border-bottom: 1px solid var(--cp-border); text-align: right; white-space: nowrap; }
    th { color: var(--cp-text-muted); font-size: .72rem; letter-spacing: .05em; text-transform: uppercase; }
    th:first-child, td:first-child { text-align: left; }
    td:first-child { font-weight: 700; }
    .fallback { color: var(--cp-warning); }
    details summary { cursor: pointer; font-weight: 700; }
    details ul { color: var(--cp-text-muted); line-height: 1.7; }
    .empty { color: var(--cp-text-muted); }
    footer { margin-top: 28px; color: var(--cp-text-muted); font-size: .8rem; }
    @media (max-width: 900px) { .grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
    @media (max-width: 560px) {
      main { width: min(100% - 20px, 1180px); padding-top: 24px; }
      .grid { grid-template-columns: 1fr; }
      .periods { width: 100%; grid-auto-flow: row; }
      .periods button { width: 100%; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">Measured consumption · modeled valuation</div>
    <h1 id="title"></h1>
    <p class="subtitle">An auditable view of tokens, prompt-cache reuse, active generation time, and estimated API-equivalent compute cost.</p>
    <p class="meta" id="meta"></p>
    <div class="notice"><strong>Not an invoice.</strong> Token counts and active time are measured from local GitHub Copilot CLI telemetry. Compute cost applies an editable rate card; billing and labor must be reconciled separately.</div>
    <div class="periods" id="periods" role="group" aria-label="Reporting period"></div>
  </header>
  <div class="grid" id="kpis"></div>
  <section class="card">
    <div class="section-head"><h2>Token composition</h2><span class="badge">Measured</span></div>
    <div class="token-bar" id="tokenBar" aria-label="Token composition"></div>
    <div class="legend" id="legend"></div>
  </section>
  <section class="card">
    <div class="section-head"><h2>Per-model breakdown</h2><span class="badge">Cache-aware</span></div>
    <div class="table-wrap"><table>
      <thead><tr><th>Model</th><th>Rate match</th><th>Input</th><th>Output</th><th>Cache read</th><th>Cache write</th><th>Active</th><th>Modeled cost</th></tr></thead>
      <tbody id="models"></tbody>
    </table></div>
  </section>
  <section class="card" id="historySection">
    <div class="section-head"><h2>Recent checkpoints</h2><span class="badge">Audit trail</span></div>
    <div class="table-wrap"><table>
      <thead><tr><th>Checkpoint</th><th>Timestamp</th><th>Cumulative cost</th><th>Delta cost</th><th>Delta input</th></tr></thead>
      <tbody id="history"></tbody>
    </table></div>
  </section>
  <details class="card">
    <summary>Methodology and evidence boundaries</summary>
    <ul>
      <li><strong>Measured:</strong> token buckets, requests, model names, and active generation duration recorded by GitHub Copilot CLI.</li>
      <li><strong>Modeled:</strong> API-equivalent compute value using the named, editable rate card. This is not Copilot billing.</li>
      <li><strong>Unavailable unless supplied separately:</strong> human oversight, loaded labor, license allocation, infrastructure, and business value.</li>
      <li>Fresh input = total input - cache read - cache write. Negative results are clamped to zero and should be investigated.</li>
      <li>Fallback-priced models are disclosed rather than silently presented as exact.</li>
    </ul>
  </details>
  <footer>Generated by AI Build Cost Toolkit. Keep raw session databases private; share the derived report only after review.</footer>
</main>
<script id="aic-data" type="application/json">__DATA__</script>
<script>
  const data = JSON.parse(document.getElementById("aic-data").textContent);
  let period = data.baseline ? "combined" : "current";
  const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const credits = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  const money = n => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: n >= 100 ? 0 : 2 }).format(n || 0);
  const compact = n => new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  const duration = ms => {
    const seconds = Math.round((ms || 0) / 1000);
    const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  };
  const subtract = (current, baseline) => {
    const fields = ["input_tokens","output_tokens","cache_read_tokens","cache_write_tokens","fresh_input_tokens","reasoning_tokens","active_ms","ai_requests","model_requests","cost_usd"];
    const totals = {};
    fields.forEach(key => totals[key] = (current.totals[key] || 0) - (baseline.totals[key] || 0));
    totals.premium_credits = null;
    const baseModels = new Map(baseline.models.map(m => [m.model, m]));
    const models = current.models.map(model => {
      const base = baseModels.get(model.model) || {};
      const copy = { ...model, cost: { ...model.cost } };
      ["input_tokens","output_tokens","cache_read_tokens","cache_write_tokens","fresh_input_tokens","reasoning_tokens","active_ms","requests"].forEach(key => copy[key] = (model[key] || 0) - (base[key] || 0));
      ["freshInput","cacheRead","cacheWrite","output","total"].forEach(key => copy.cost[key] = (model.cost[key] || 0) - ((base.cost || {})[key] || 0));
      return copy;
    }).filter(model => model.cost.total > 0 || model.input_tokens > 0 || model.output_tokens > 0);
    return {
      ...current,
      totals,
      models,
      scope: { ...current.scope, repository: `${current.scope.repository} · since baseline` },
      evidence: { ...current.evidence, premiumCredits: "unavailable" }
    };
  };
  const selected = () => period === "initial" ? data.baseline : period === "increment" ? subtract(data.current, data.baseline) : data.current;
  const renderPeriods = () => {
    const host = document.getElementById("periods");
    const options = data.baseline ? [["initial","Initial"],["increment","Since baseline"],["combined","Combined"]] : [["current","Current"]];
    host.innerHTML = options.map(([value,label]) => `<button type="button" data-period="${value}" aria-pressed="${period === value}">${label}</button>`).join("");
    host.querySelectorAll("button").forEach(button => button.addEventListener("click", () => { period = button.dataset.period; render(); }));
  };
  const render = () => {
    const report = selected(), t = report.totals, scope = report.scope;
    document.getElementById("title").textContent = data.title;
    document.getElementById("meta").textContent = `${scope.repository || "Unspecified repository"} · ${scope.sessionCount ?? "?"} sessions · rate card ${report.rateCard.version}`;
    const kpis = [
      ["Modeled compute", money(t.cost_usd), "Editable rate-card valuation"],
      ["Tokens processed", compact((t.input_tokens || 0) + (t.output_tokens || 0)), `${compact(t.cache_read_tokens)} cache-read`],
      ["Active generation", duration(t.active_ms), "Measured model response time"],
      ["Premium credits", t.premium_credits == null ? "Unavailable" : credits.format(t.premium_credits), report.evidence.premiumCredits],
      ["AI requests", nf.format(t.ai_requests || scope.requestCount || 0), `${nf.format(t.model_requests || 0)} per-model calls`],
      ["Cache reuse", t.input_tokens ? `${Math.round(100 * t.cache_read_tokens / t.input_tokens)}%` : "0%", "Share of input served from cache"],
      ["Fresh input", compact(t.fresh_input_tokens), "Input excluding cache buckets"],
      ["Output", compact(t.output_tokens), "Generated tokens"],
    ];
    document.getElementById("kpis").innerHTML = kpis.map(k => `<div class="card"><div class="kpi-label">${esc(k[0])}</div><div class="kpi-value">${esc(k[1])}</div><div class="kpi-detail">${esc(k[2])}</div></div>`).join("");
    const parts = [
      ["fresh","Fresh input",t.fresh_input_tokens || 0],
      ["read","Cache read",t.cache_read_tokens || 0],
      ["write","Cache write",t.cache_write_tokens || 0],
      ["output","Output",t.output_tokens || 0],
    ];
    const total = parts.reduce((sum,p) => sum + p[2], 0) || 1;
    document.getElementById("tokenBar").innerHTML = parts.map(p => `<span class="${p[0]}" style="width:${100*p[2]/total}%" title="${p[1]}: ${nf.format(p[2])}"></span>`).join("");
    document.getElementById("legend").innerHTML = parts.map(p => `<span><i class="${p[0]}"></i>${esc(p[1])} ${esc(compact(p[2]))}</span>`).join("");
    document.getElementById("models").innerHTML = report.models.map(model => `<tr>
      <td class="${model.rate_match === "default" || model.rate_match === "prefix" ? "fallback" : ""}">${esc(model.model)}</td>
      <td class="${model.rate_match === "default" || model.rate_match === "prefix" ? "fallback" : ""}">${esc(model.rate_match || "unknown")}</td>
      <td>${esc(compact(model.input_tokens))}</td><td>${esc(compact(model.output_tokens))}</td>
      <td>${esc(compact(model.cache_read_tokens))}</td><td>${esc(compact(model.cache_write_tokens))}</td>
      <td>${esc(duration(model.active_ms))}</td><td>${esc(money(model.cost.total))}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="empty">No model data for this period.</td></tr>`;
    renderPeriods();
  };
  const history = document.getElementById("history");
  if (data.ledger.length) {
    history.innerHTML = data.ledger.slice().reverse().map(row => `<tr>
      <td>${esc(row.label)}${row.scope_change === "true" ? " · scope reset" : ""}</td><td>${esc(row.timestamp)}</td>
      <td>${esc(money(Number(row.cumulative_cost_usd)))}</td><td>${esc(money(Number(row.delta_cost_usd)))}</td>
      <td>${esc(compact(Number(row.delta_input_tokens)))}</td>
    </tr>`).join("");
  } else {
    document.getElementById("historySection").hidden = true;
  }
  render();
</script>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        document.replace("__TITLE__", html.escape(title)).replace("__DATA__", safe_payload),
        encoding="utf-8",
    )
