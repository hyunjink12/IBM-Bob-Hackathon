/**
 * Panel 1 — latest market snapshot with per-series staleness.
 */
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
        {overview.metrics.map((metric) => (
          <article key={metric.key} className="metric-card">
            <h3>{metric.label}</h3>
            <p className="metric-card__value">
              {metric.value == null ? '—' : metric.value.toFixed(2)}
              <span className="metric-card__unit">{metric.unit}</span>
            </p>
            <p className="metric-card__description">{metric.description}</p>
            <p className="metric-card__updated">
              Updated: {metric.last_updated ?? 'unknown'}
            </p>
          </article>
        ))}
        <article className="metric-card metric-card--wasde">
          <h3>WASDE Corn for Ethanol</h3>
          <p className="metric-card__value">
            {overview.wasde.value_mbu == null ? '—' : overview.wasde.value_mbu.toFixed(0)}
            <span className="metric-card__unit">M bu</span>
          </p>
          <p className="metric-card__description">
            Monthly USDA demand anchor
            {overview.wasde.delta_mbu != null
              ? ` (${overview.wasde.delta_mbu >= 0 ? '+' : ''}${overview.wasde.delta_mbu.toFixed(0)} vs prior)`
              : ''}
          </p>
          <p className="metric-card__updated">
            Report: {overview.wasde.report_month ?? '—'}
          </p>
        </article>
      </div>
    </section>
  )
}
