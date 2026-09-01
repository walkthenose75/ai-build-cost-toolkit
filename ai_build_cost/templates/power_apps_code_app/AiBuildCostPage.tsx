import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import './AiBuildCostPage.css'

export type AicRateMatch = 'exact' | 'alias' | 'prefix' | 'default'

export type AicModelReport = {
  model: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  fresh_input_tokens: number
  reasoning_tokens: number
  active_ms: number
  requests: number
  rate_key: string
  rate_match: AicRateMatch
  used_fallback_rate: boolean
  cost: {
    freshInput: number
    cacheRead: number
    cacheWrite: number
    output: number
    total: number
  }
}

export type AicReport = {
  schemaVersion: 1
  generatedAt: string
  sourceGeneratedAt?: string | null
  scope: {
    repository?: string
    sessionCount?: number | null
    requestCount?: number | null
    creditKnownRequestCount?: number | null
    firstActivity?: string | null
    lastActivity?: string | null
    calendarDays?: number | null
    filter?: {
      since?: string | null
      match?: string
      sessionScope?: string
      sessionFingerprint?: string | null
    }
  }
  evidence: {
    tokens: 'measured'
    activeTime: 'measured'
    premiumCredits: 'measured' | 'unavailable'
    computeCost: 'modeled'
  }
  rateCard: {
    version: string
    currency: string
    fingerprint: string
    fallbackRatedModels: string[]
    prefixRatedModels: string[]
  }
  totals: {
    input_tokens: number
    output_tokens: number
    cache_read_tokens: number
    cache_write_tokens: number
    fresh_input_tokens: number
    reasoning_tokens: number
    active_ms: number
    model_requests: number
    ai_requests: number
    cost_usd: number
    premium_credits: number | null
  }
  models: AicModelReport[]
}

type Period = 'initial' | 'increment' | 'combined'

type Props = {
  report: AicReport
  baseline?: AicReport
  title?: string
}

const COUNTERS = [
  'input_tokens',
  'output_tokens',
  'cache_read_tokens',
  'cache_write_tokens',
  'fresh_input_tokens',
  'reasoning_tokens',
  'active_ms',
  'model_requests',
  'ai_requests',
  'cost_usd',
] as const

const MODEL_COUNTERS = [
  'input_tokens',
  'output_tokens',
  'cache_read_tokens',
  'cache_write_tokens',
  'fresh_input_tokens',
  'reasoning_tokens',
  'active_ms',
  'requests',
] as const

function subtract(current: number, baseline: number, label: string): number {
  const value = current - baseline
  if (value < -0.000001) throw new Error(`Baseline exceeds current report for ${label}`)
  return Math.max(0, value)
}

function deriveIncrement(current: AicReport, baseline: AicReport): AicReport {
  if (current.scope.repository !== baseline.scope.repository) {
    throw new Error('Baseline and current reports belong to different repositories')
  }
  if (current.rateCard.fingerprint !== baseline.rateCard.fingerprint) {
    throw new Error('Baseline and current reports use different rate cards')
  }
  if (current.rateCard.version !== baseline.rateCard.version) {
    throw new Error('Baseline and current reports use different rate-card versions')
  }
  if (JSON.stringify(current.scope.filter ?? {}) !== JSON.stringify(baseline.scope.filter ?? {})) {
    throw new Error('Baseline and current reports use different collection filters')
  }

  const totals = { ...current.totals, premium_credits: null }
  for (const counter of COUNTERS) {
    totals[counter] = subtract(current.totals[counter], baseline.totals[counter], counter)
  }

  const baselineModels = new Map(baseline.models.map((model) => [model.model, model]))
  const models = current.models.map((model) => {
    const prior = baselineModels.get(model.model)
    const next = { ...model, cost: { ...model.cost } }
    for (const counter of MODEL_COUNTERS) {
      next[counter] = subtract(model[counter], prior?.[counter] ?? 0, `${model.model}.${counter}`)
    }
    for (const counter of ['freshInput', 'cacheRead', 'cacheWrite', 'output', 'total'] as const) {
      next.cost[counter] = subtract(model.cost[counter], prior?.cost[counter] ?? 0, `${model.model}.cost.${counter}`)
    }
    return next
  }).filter((model) => model.input_tokens > 0 || model.output_tokens > 0 || model.cost.total > 0)

  for (const model of baseline.models) {
    if (!current.models.some((candidate) => candidate.model === model.model)) {
      throw new Error(`Baseline model ${model.model} is missing from the current report`)
    }
  }

  return {
    ...current,
    evidence: { ...current.evidence, premiumCredits: 'unavailable' },
    scope: { ...current.scope, repository: `${current.scope.repository ?? 'Project'} - since baseline` },
    totals,
    models,
  }
}

function money(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value)
}

function compact(value: number): string {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function integer(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

function duration(milliseconds: number): string {
  const minutes = Math.round(milliseconds / 60_000)
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function AiBuildCostPage({
  report,
  baseline,
  title = 'AI Build Cost',
}: Props) {
  const [period, setPeriod] = useState<Period>('combined')
  const selected = useMemo(() => {
    if (!baseline || period === 'combined') return report
    return period === 'initial' ? baseline : deriveIncrement(report, baseline)
  }, [baseline, period, report])

  const totalTokens = selected.totals.input_tokens + selected.totals.output_tokens
  const cacheRatio = selected.totals.input_tokens
    ? selected.totals.cache_read_tokens / selected.totals.input_tokens
    : 0
  const tokenSegments = [
    { key: 'fresh', label: 'Fresh input', value: selected.totals.fresh_input_tokens },
    { key: 'read', label: 'Cache read', value: selected.totals.cache_read_tokens },
    { key: 'write', label: 'Cache write', value: selected.totals.cache_write_tokens },
    { key: 'output', label: 'Output', value: selected.totals.output_tokens },
  ]
  const segmentTotal = tokenSegments.reduce((sum, segment) => sum + segment.value, 0) || 1
  const reviewModels = [
    ...selected.rateCard.prefixRatedModels,
    ...selected.rateCard.fallbackRatedModels,
  ]

  const kpis = [
    ['Modeled compute', money(selected.totals.cost_usd), 'Rate-card valuation, not an invoice'],
    ['Tokens processed', compact(totalTokens), `${compact(selected.totals.cache_read_tokens)} cache-read`],
    ['Active generation', duration(selected.totals.active_ms), 'Measured model response time'],
    [
      'Premium credits',
      selected.totals.premium_credits == null
        ? 'Unavailable'
        : new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(selected.totals.premium_credits),
      selected.evidence.premiumCredits,
    ],
    ['AI requests', integer(selected.totals.ai_requests), `${integer(selected.totals.model_requests)} model calls`],
    ['Cache reuse', `${Math.round(cacheRatio * 100)}%`, 'Share of input served from cache'],
    ['Fresh input', compact(selected.totals.fresh_input_tokens), 'Excludes cache buckets'],
    ['Output', compact(selected.totals.output_tokens), 'Generated tokens'],
  ]

  return (
    <main className="aic-code-report">
      <header className="aic-code-report__header">
        <span className="aic-code-report__eyebrow">Measured consumption · modeled valuation</span>
        <h1>{title}</h1>
        <p>
          Use this page inside the Power Apps Code App being measured. It reads a
          committed AIC report and does not query local telemetry from the browser.
        </p>
        <small>
          {selected.scope.repository ?? 'Project'} · {selected.scope.sessionCount ?? '?'} sessions ·
          rate card {selected.rateCard.version}
        </small>
      </header>

      {baseline ? (
        <div className="aic-code-report__periods" role="group" aria-label="Reporting period">
          {([
            ['initial', 'Initial Build'],
            ['increment', 'Since Baseline'],
            ['combined', 'Combined'],
          ] as const).map(([value, label]) => (
            <button
              type="button"
              key={value}
              aria-pressed={period === value}
              onClick={() => setPeriod(value)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      <aside className="aic-code-report__notice">
        <strong>Evidence boundary:</strong> tokens and generation time are measured;
        compute is modeled from the named rate card. Labor, licensing, hosting, and
        business value are not inferred.
      </aside>

      {reviewModels.length ? (
        <aside className="aic-code-report__warning">
          <strong>Rate review required:</strong> {reviewModels.join(', ')} used a
          prefix or default rate. Add an exact key or alias before quoting the result.
        </aside>
      ) : null}

      <section className="aic-code-report__kpis" aria-label="AI consumption metrics">
        {kpis.map(([label, value, detail]) => (
          <article className="aic-code-report__card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{detail}</small>
          </article>
        ))}
      </section>

      <section className="aic-code-report__panel">
        <h2>Token composition</h2>
        <div className="aic-code-report__token-bar" aria-label="Token composition">
          {tokenSegments.map((segment) => (
            <span
              className={`aic-code-report__token-${segment.key}`}
              key={segment.key}
              title={`${segment.label}: ${integer(segment.value)}`}
              style={{ '--aic-segment-width': `${(segment.value / segmentTotal) * 100}%` } as CSSProperties}
            />
          ))}
        </div>
        <div className="aic-code-report__legend">
          {tokenSegments.map((segment) => (
            <span key={segment.key}>{segment.label}: {compact(segment.value)}</span>
          ))}
        </div>
      </section>

      <section className="aic-code-report__panel">
        <h2>Per-model breakdown</h2>
        <div className="aic-code-report__table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th><th>Rate</th><th>Input</th><th>Output</th>
                <th>Cache read</th><th>Active</th><th>Modeled cost</th>
              </tr>
            </thead>
            <tbody>
              {selected.models.map((model) => (
                <tr key={model.model}>
                  <td>{model.model}</td>
                  <td data-review={model.rate_match === 'prefix' || model.rate_match === 'default'}>
                    {model.rate_match}
                  </td>
                  <td>{compact(model.input_tokens)}</td>
                  <td>{compact(model.output_tokens)}</td>
                  <td>{compact(model.cache_read_tokens)}</td>
                  <td>{duration(model.active_ms)}</td>
                  <td>{money(model.cost.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <details className="aic-code-report__panel">
        <summary>Methodology</summary>
        <p>
          Fresh input equals total input minus cache-read and cache-write tokens.
          Initial and Combined are cumulative snapshots. Since Baseline is derived
          as current minus the immutable baseline; checkpoints are never added.
        </p>
      </details>
    </main>
  )
}
