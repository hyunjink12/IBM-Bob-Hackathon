/**
 * Panel — Ethanol economics decomposed into physical drivers + the regulatory
 * D6 RIN value layer.
 *
 * Casual: what makes up today's plant P&L, and separately the compliance-market
 * value attached to the ethanol gallon.
 *
 * Physical drivers (ethanol/DDGS/corn oil revenue minus corn/gas/opex costs)
 * sum to the plant operating margin the plant actually realizes from the
 * crush. The D6 RIN value is rendered under a separate REGULATORY subheading
 * with a divider — it is a compliance-market value derived from EPA RIN
 * transaction prices, NOT assumed to be dollar-for-dollar producer revenue
 * (pass-through economics to obligated parties are out of scope).
 */
export function MarginCompositionPanel({ composition }) {
  if (!composition) {
    return (
      <section className="panel">
        <header className="panel__header">
          <h2>Ethanol Economics Decomposition</h2>
        </header>
        <p className="empty-state">Loading decomposition…</p>
      </section>
    )
  }

  const physical = (composition.physical_components ?? composition.components ?? []).filter(
    (c) => c.included !== false || c.value_per_bushel !== 0,
  )
  const regulatory = (composition.regulatory_components ?? []).filter(
    (c) => c.included !== false,
  )
  const allShown = [...physical, ...regulatory]
  const maxAbs = Math.max(
    ...allShown.map((c) => Math.abs(c.value_per_bushel ?? 0)),
    0.01,
  )

  const plantOperatingMargin =
    composition.plant_operating_margin_per_bushel ?? composition.margin_per_bushel
  const d6RinValue = composition.d6_rin_value_per_bushel ?? 0

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Ethanol Economics Decomposition</h2>
        <span className="panel__meta">$/bu · as of {composition.as_of}</span>
      </header>

      <div className="composition">
        <div className="composition__section-label">Physical / Operating</div>
        {physical.map((c) => (
          <CompositionRow key={c.label} row={c} maxAbs={maxAbs} />
        ))}
        <div className="composition__total">
          <span className="composition__total-label">Plant operating margin</span>
          <span className="composition__total-value">
            {formatUsd(plantOperatingMargin)}
          </span>
        </div>

        {regulatory.length > 0 && (
          <>
            <div className="composition__divider" />
            <div className="composition__section-label">Regulatory</div>
            {regulatory.map((c) => (
              <CompositionRow key={c.label} row={c} maxAbs={maxAbs} />
            ))}
            <p className="composition__reg-note">
              Regulatory-value equivalent for scale — not assumed to be direct
              producer operating revenue.
            </p>
          </>
        )}
      </div>
    </section>
  )
}

function CompositionRow({ row, maxAbs }) {
  const value = row.value_per_bushel ?? 0
  const widthPct = Math.min(100, (Math.abs(value) / maxAbs) * 100)
  const kindClass =
    row.kind === 'regulatory'
      ? 'is-regulatory'
      : row.kind === 'revenue'
        ? 'is-revenue'
        : 'is-cost'
  return (
    <div className={`composition__row ${kindClass}`} title={row.tooltip ?? undefined}>
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
