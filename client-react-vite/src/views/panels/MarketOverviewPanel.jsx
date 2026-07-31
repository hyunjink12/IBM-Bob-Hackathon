/**
 * Panel 1 — latest market snapshot with per-series staleness.
 */

const STALE_AFTER_DAYS = 7  // series with age_days >= this get a "stale" badge (matches backend tape)

/** "2026-07-30T13:19:30.897263-04:00" → "Jul 30, 2026, 1:19 PM ET" */
function formatTimestamp(iso) {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  })
}

/**
 * Calendar-days between the given ISO timestamp and today, in the viewer's
 * local timezone. Matches the backend tape's `(date.today() - dt.date()).days`
 * so the "20d stale" card and "STALE 21d" tape can't disagree by 1 day for
 * end-of-day fetch timestamps.
 */
function daysSince(iso) {
  if (!iso) return null
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return null
  const thenDay = new Date(then.getFullYear(), then.getMonth(), then.getDate())
  const today = new Date()
  const todayDay = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((todayDay.getTime() - thenDay.getTime()) / (1000 * 60 * 60 * 24))
}

/** Ethanol stocks display with 3 decimals — matches trader convention post-fix. */
function formatValue(metric) {
  if (metric.value == null) return '—'
  if (metric.key === 'ethanol_stocks') return metric.value.toFixed(2)
  if (metric.key === 'ethanol_production') return metric.value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  return metric.value.toFixed(2)
}

export function MarketOverviewPanel({ overview }) {
  if (!overview) {
    return <section className="panel">Loading market overview…</section>
  }

  return (
    <section className="panel panel--overview">
      <header className="panel__header">
        <h2>Market Overview</h2>
        <span className="panel__meta">As of {overview.as_of}</span>
      </header>
      <div className="metric-grid">
        {overview.metrics.map((metric) => {
          const age = daysSince(metric.last_updated)
          const isStale = age != null && age >= STALE_AFTER_DAYS
          return (
            <article key={metric.key} className={`metric-card${isStale ? ' metric-card--stale' : ''}`}>
              <div className="metric-card__label-row">
                <h3>{metric.label}</h3>
                {isStale && <span className="metric-card__stale-badge">{age}d stale</span>}
              </div>
              <p className="metric-card__value">
                {formatValue(metric)}
                <span className="metric-card__unit">{metric.unit}</span>
              </p>
              <p className="metric-card__description">{metric.description}</p>
              <p className="metric-card__updated">
                Updated {formatTimestamp(metric.last_updated) ?? 'unknown'}
              </p>
            </article>
          )
        })}
        <WasdeCard wasde={overview.wasde} />
      </div>
    </section>
  )
}

/** Separate WASDE card with billion-bushel formatting (USDA-friendly for annual figures). */
function WasdeCard({ wasde }) {
  const bbu = wasde.value_mbu == null ? null : wasde.value_mbu / 1000
  const deltaBbu = wasde.delta_mbu == null ? null : wasde.delta_mbu / 1000
  return (
    <article className="metric-card metric-card--wasde">
      <div className="metric-card__label-row">
        <h3>Corn for Ethanol</h3>
      </div>
      <p className="metric-card__value">
        {bbu == null ? '—' : bbu.toFixed(2)}
        <span className="metric-card__unit">B bu</span>
      </p>
      <p className="metric-card__description">
        Monthly USDA WASDE demand anchor
        {deltaBbu != null
          ? ` (${deltaBbu >= 0 ? '+' : ''}${deltaBbu.toFixed(2)} vs prior)`
          : ''}
      </p>
      <p className="metric-card__updated">
        Report {wasde.report_month ?? '—'}
      </p>
    </article>
  )
}
