/**
 * Panel 4 — inventory/production stress snapshot plus rule-based warning cards.
 *
 * Casual: always show tanks + run-rate context, then any active alerts.
 *
 * Calm markets used to render only an empty-state sentence, which looked like
 * missing data. The stress block keeps levels and deltas visible even when no
 * warning rules fire.
 */
export function WarningSignalsPanel({ warnings }) {
  if (!warnings) {
    return <section className="panel">Loading warning signals…</section>
  }

  const stress = warnings.stress ?? null
  const activeWarnings = warnings.warnings ?? []

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
            <article
              key={warning.signal_type}
              className={`warning-card warning-card--${warning.severity}`}
            >
              <h3>{warning.signal_type.replaceAll('_', ' ')}</h3>
              <p>{warning.message}</p>
            </article>
          ))}
        </div>
      )}
    </section>
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
