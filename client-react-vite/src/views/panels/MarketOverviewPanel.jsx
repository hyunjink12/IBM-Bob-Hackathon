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

/**
 * Weekly-downsampled sparkline of the blender's advantage over the last year.
 * Zero axis is drawn as a subtle horizontal line so the sign of the spread
 * reads at a glance. Latest point gets a filled dot.
 */
function BlenderAdvantageSparkline({ series }) {
  if (!series || series.length < 2) return null
  const values = series.map((p) => p.value)
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 0)
  const range = max === min ? 1 : max - min

  // Larger viewBox + preserveAspectRatio="none" so the SVG scales up to fill
  // whatever width the parent gives it while staying at a comfortable height.
  const VW = 400
  const VH = 80
  const pad = { t: 6, b: 6, l: 2, r: 2 }
  const iW = VW - pad.l - pad.r
  const iH = VH - pad.t - pad.b

  const points = values.map((v, i) => ({
    x: pad.l + (i / (values.length - 1)) * iW,
    y: pad.t + iH - ((v - min) / range) * iH,
  }))
  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(' ')

  const zeroY = pad.t + iH - ((0 - min) / range) * iH
  const areaBase = zeroY >= pad.t && zeroY <= pad.t + iH ? zeroY : pad.t + iH
  const areaPath =
    `${linePath} L${points[points.length - 1].x.toFixed(1)},${areaBase.toFixed(1)}` +
    ` L${points[0].x.toFixed(1)},${areaBase.toFixed(1)} Z`

  return (
    <svg
      className="blending-card__sparkline"
      viewBox={`0 0 ${VW} ${VH}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="blenderAdvGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4589ff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#4589ff" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {zeroY >= pad.t && zeroY <= pad.t + iH && (
        <line
          x1={pad.l} y1={zeroY} x2={pad.l + iW} y2={zeroY}
          stroke="#3a4a63" strokeWidth="0.6" strokeDasharray="3,3"
        />
      )}
      <path d={areaPath} fill="url(#blenderAdvGrad)" stroke="none" />
      <path
        d={linePath}
        fill="none"
        stroke="#4589ff"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** English ordinal suffix: 1 → "st", 2 → "nd", 3 → "rd", else "th". Handles teens. */
function ordinalSuffix(n) {
  const rem100 = n % 100
  if (rem100 >= 11 && rem100 <= 13) return 'th'
  const rem10 = n % 10
  if (rem10 === 1) return 'st'
  if (rem10 === 2) return 'nd'
  if (rem10 === 3) return 'rd'
  return 'th'
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
        <RbobCard blending={overview.blending_economics} />
        <BlendingEconomicsCard blending={overview.blending_economics} />
      </div>
    </section>
  )
}

/**
 * RBOB gasoline card, rendered in the metric grid alongside the blending
 * economics span. Value comes from the blending payload (see backend note in
 * OVERVIEW_SERIES about why RBOB isn't a crush input).
 */
function RbobCard({ blending }) {
  if (!blending) return null
  const age = daysSince(blending.rbob_last_updated)
  const isStale = age != null && age >= STALE_AFTER_DAYS
  return (
    <article className={`metric-card${isStale ? ' metric-card--stale' : ''}`}>
      <div className="metric-card__label-row">
        <h3>RBOB</h3>
        {isStale && <span className="metric-card__stale-badge">{age}d stale</span>}
      </div>
      <p className="metric-card__value">
        {blending.rbob_usd_per_gallon.toFixed(2)}
        <span className="metric-card__unit">$/gal</span>
      </p>
      <p className="metric-card__description">NYMEX RBOB futures — ethanol&rsquo;s blendstock competitor</p>
      <p className="metric-card__updated">
        Updated {formatTimestamp(blending.rbob_last_updated) ?? 'unknown'}
      </p>
    </article>
  )
}

/**
 * Bottom-of-panel derived-signal card: blender's advantage after RIN credit.
 *
 * Casual: how much cheaper ethanol is than RBOB after the RIN gets subtracted.
 *
 * Positive = refiners push blend rates up. Negative = they resist. This isn't
 * a raw price like the tiles above — it's the actual decision refiners make
 * every day about whether to blend more ethanol. See README "Blending
 * economics" section for the RIN-credit rationale and threshold caveat.
 */
function BlendingEconomicsCard({ blending }) {
  if (!blending) return null
  const advantage = blending.blender_advantage_usd_per_gallon
  const sign = advantage >= 0 ? '+' : '−'
  const magnitude = Math.abs(advantage).toFixed(2)
  // Reuse the app-wide signal-chip vocabulary so the regime badge reads
  // identically to the crush margin signal chip (RICH / WEAK / NORMAL).
  const signalVariant = {
    favor_ethanol: 'rich',
    resist_ethanol: 'weak',
    indifference: 'normal',
  }[blending.regime_direction] || 'normal'
  const regimeChipText = {
    favor_ethanol: 'FAVOR ETHANOL',
    resist_ethanol: 'RESIST ETHANOL',
    indifference: 'INDIFFERENT',
  }[blending.regime_direction] || blending.regime_label
  return (
    <article className="blending-card">
      <div className="blending-card__header">
        <h3>Blending Economics</h3>
      </div>
      <div className="blending-card__body">
        <div className="blending-card__value-block">
          <p className="blending-card__value">
            {sign}${magnitude}
            <span className="blending-card__unit">/gal</span>
          </p>
          <p className="blending-card__caption">
            blender&rsquo;s advantage after RIN credit
          </p>
          <span className={`signal signal--${signalVariant} blending-card__regime-inline`}>
            {regimeChipText}
          </span>
        </div>
        {blending.percentile_1y_pct != null && blending.sparkline_1y?.length > 1 && (
          <div className="blending-card__spark-block">
            <BlenderAdvantageSparkline series={blending.sparkline_1y} />
            <p className="blending-card__spark-caption">
              <strong className="blending-card__percentile-inline">
                {blending.percentile_1y_pct}
                <span className="blending-card__percentile-suffix">
                  {ordinalSuffix(blending.percentile_1y_pct)}
                </span>
              </strong>
              {' '}percentile · trailing 1Y
            </p>
          </div>
        )}
      </div>
      <div className="blending-card__footer">
        <span>
          RBOB <strong>${blending.rbob_usd_per_gallon.toFixed(2)}</strong>
        </span>
        <span className="blending-card__op">·</span>
        <span>
          ethanol <strong>${blending.ethanol_usd_per_gallon.toFixed(2)}</strong>
        </span>
        {blending.rin_included && (
          <>
            <span className="blending-card__op">·</span>
            <span>
              D6 RIN <strong>${blending.d6_rin_usd_per_gallon.toFixed(2)}</strong>
            </span>
          </>
        )}
        {!blending.rin_included && (
          <span className="blending-card__no-rin">(RIN unavailable — physical spread only)</span>
        )}
      </div>
    </article>
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
