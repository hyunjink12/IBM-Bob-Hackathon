/**
 * Panel — CARD crush margin decomposed into its six drivers.
 *
 * Casual: what's making up today's margin, cent by cent.
 *
 * Pairs next to Warnings on Physical tab. Every row is a lever a plant
 * operator or physical trader can hedge or price. Bar length is scaled to
 * the largest absolute component so the visual weight matches the driver's
 * contribution.
 */
export function MarginCompositionPanel({ composition }) {
  if (!composition) {
    return (
      <section className="panel">
        <header className="panel__header">
          <h2>Margin Composition</h2>
        </header>
        <p className="empty-state">Loading margin decomposition…</p>
      </section>
    )
  }

  const components = composition.components ?? []
  const shown = components.filter(
    (c) => c.included !== false || c.value_per_bushel !== 0,
  )
  const maxAbs = Math.max(
    ...shown.map((c) => Math.abs(c.value_per_bushel ?? 0)),
    0.01,
  )

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Margin Composition</h2>
        <span className="panel__meta">$/bu · as of {composition.as_of}</span>
      </header>

      <div className="composition">
        {shown.map((c) => (
          <CompositionRow key={c.label} row={c} maxAbs={maxAbs} />
        ))}
        <div className="composition__total">
          <span className="composition__total-label">Crush margin</span>
          <span className="composition__total-value">
            {formatUsd(composition.margin_per_bushel)}
          </span>
        </div>
      </div>
    </section>
  )
}

function CompositionRow({ row, maxAbs }) {
  const value = row.value_per_bushel ?? 0
  const widthPct = Math.min(100, (Math.abs(value) / maxAbs) * 100)
  const kindClass = row.kind === 'revenue' ? 'is-revenue' : 'is-cost'
  return (
    <div className={`composition__row ${kindClass}`}>
      <span className="composition__label">{row.label}</span>
      <div className="composition__bar-wrap">
        <div
          className="composition__bar"
          style={{ width: `${widthPct}%` }}
          aria-hidden="true"
        />
      </div>
      <span className="composition__value">{formatUsd(value)}</span>
    </div>
  )
}

function formatUsd(value) {
  if (value == null || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}$${Math.abs(value).toFixed(3)}`
}
