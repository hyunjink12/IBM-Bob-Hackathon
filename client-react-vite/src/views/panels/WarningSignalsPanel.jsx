/**
 * Panel 4 — inventory/production stress snapshot plus rule-based warning cards.
 *
 * Casual: always show tanks + run-rate context, then any active alerts.
 *
 * Calm markets used to render only an empty-state sentence, which looked like
 * missing data. The stress block keeps levels and deltas visible even when no
 * warning rules fire.
 */
export function WarningSignalsPanel({ warnings, backtest }) {
  if (!warnings) {
    return <section className="panel">Loading warning signals…</section>
  }

  const stress = warnings.stress ?? null
  const activeWarnings = warnings.warnings ?? []
  const reportsBySignalType = new Map(
    (backtest?.reports ?? []).map((r) => [r.signal_type, r]),
  )

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Inventory / Production Stress</h2>
        <span className="panel__meta">As of {warnings.as_of ?? '—'}</span>
      </header>

      {stress ? <StressSnapshot stress={stress} /> : null}

      {activeWarnings.length === 0 ? (
        <p className="empty-state">
          {stress?.status_message ??
            'No active warning signals for the latest session.'}
        </p>
      ) : (
        <div className="warning-grid">
          {activeWarnings.map((warning) => (
            <WarningCard
              key={warning.signal_type}
              warning={warning}
              report={reportsBySignalType.get(warning.signal_type)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

/**
 * Single warning card with rule message, suggested trade, and backtest track record.
 *
 * Casual: what fired, what to consider trading, and how the rule has done historically.
 */
function WarningCard({ warning, report }) {
  return (
    <article className={`warning-card warning-card--${warning.severity}`}>
      <h3>{warning.signal_type.replaceAll('_', ' ')}</h3>
      <p>{warning.message}</p>
      {warning.suggested_trade ? (
        <p className="warning-card__trade">
          <strong>Possible trade:</strong> {warning.suggested_trade}
        </p>
      ) : null}
      {report ? <BacktestStrip report={report} /> : null}
    </article>
  )
}

/**
 * One-line track record for the underlying rule.
 *
 * Casual: fired N× • 30d median $X • hit rate Y%.
 */
function BacktestStrip({ report }) {
  const median30 = report.median_move_by_horizon?.['30']
  const hitRate30 = report.hit_rate_by_horizon?.['30']
  const parts = [`fired ${report.fire_count}×`]
  if (median30 != null) {
    const sign = median30 >= 0 ? '+' : ''
    parts.push(`30d median ${sign}$${median30.toFixed(2)}`)
  }
  if (hitRate30 != null) {
    parts.push(`hit rate ${(hitRate30 * 100).toFixed(0)}%`)
  }
  return (
    <p className="warning-card__backtest">
      Track record: {parts.join(' • ')}
    </p>
  )
}

/**
 * Compact stocks / production / margin status strip.
 *
 * Casual: the always-on numbers so the panel never looks blank.
 */
function StressSnapshot({ stress }) {
  return (
    <div className={`stress-snapshot stress-snapshot--${stress.status}`}>
      <div className="stress-snapshot__status">
        <span className="stress-snapshot__badge">{stress.status}</span>
        {stress.margin_signal_label ? (
          <span className={`signal signal--${stress.margin_signal_label}`}>
            margin {stress.margin_signal_label}
          </span>
        ) : null}
      </div>
      <div className="stress-snapshot__metrics">
        <StressMetric
          label="Ethanol stocks"
          value={formatNumber(stress.stocks_mmbbl, 2)}
          unit="MMbbl"
          delta={formatPct(stress.stocks_change_28d_pct)}
          deltaLabel="28d"
        />
        <StressMetric
          label="Production"
          value={formatNumber(stress.production_mbpd, 0)}
          unit="Mbpd"
          delta={formatPct(stress.production_vs_180d_avg_pct)}
          deltaLabel="vs 180d avg"
        />
      </div>
    </div>
  )
}

/**
 * One metric cell inside the stress snapshot.
 *
 * Casual: label, big number, tiny delta.
 */
function StressMetric({ label, value, unit, delta, deltaLabel }) {
  return (
    <article className="stress-metric">
      <h3>{label}</h3>
      <p className="stress-metric__value">
        {value}
        <span className="stress-metric__unit">{unit}</span>
      </p>
      <p className="stress-metric__delta">
        {delta == null ? '—' : delta} {deltaLabel}
      </p>
    </article>
  )
}

function formatNumber(value, digits) {
  if (value == null || Number.isNaN(value)) {
    return '—'
  }
  return Number(value).toFixed(digits)
}

function formatPct(value) {
  if (value == null || Number.isNaN(value)) {
    return null
  }
  const pct = value * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}
