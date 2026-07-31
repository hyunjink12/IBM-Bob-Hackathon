import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 2 — crush margin centerpiece with z-score and signal label.
 */
/** Format a decimal fraction (0.023) as a signed percent ("+2.3%"). */
function formatPct(fraction, digits = 1) {
  if (fraction == null || Number.isNaN(fraction)) return null
  const pct = fraction * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

/** Format an ISO date as "Wed Jul 30, 2026" for release popup titles. */
function formatReleaseDate(iso) {
  if (!iso) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  const d = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Direction bucket for signed deltas (drives popup color). */
function deltaDirection(fraction) {
  if (fraction == null || Number.isNaN(fraction) || fraction === 0) return 'flat'
  return fraction > 0 ? 'up' : 'down'
}

/** Shape EIA release records into the events prop the chart consumes. */
function buildReleaseEvents(releases) {
  if (!releases?.length) return undefined
  return releases.map((r) => {
    const rows = []
    if (r.stocks_mmbbl != null) {
      rows.push({
        label: 'Stocks',
        value: `${r.stocks_mmbbl.toFixed(2)} MMbbl`,
        delta: formatPct(r.stocks_wow_pct),
        deltaDirection: deltaDirection(r.stocks_wow_pct),
      })
    }
    if (r.production_mbpd != null) {
      rows.push({
        label: 'Production',
        value: `${Math.round(r.production_mbpd).toLocaleString()} Mb/d`,
        delta: formatPct(r.production_wow_pct),
        deltaDirection: deltaDirection(r.production_wow_pct),
      })
    }
    return {
      date: r.date,
      tooltip: {
        title: `EIA · ${formatReleaseDate(r.date)}`,
        rows,
      },
    }
  })
}

export function CrushMarginPanel({ margins, config, eiaReleases }) {
  if (!margins) {
    return <section className="panel">Loading crush margin…</section>
  }

  const current = margins.current
  const signalClass = current ? `signal signal--${current.signal_label}` : 'signal'

  return (
    <section className="panel panel--hero">
      <header className="panel__header">
        <h2>Ethanol Crush Margin</h2>
        <span className="panel__meta">
          {margins.range} · {margins.granularity}
        </span>
      </header>

      {current && (
        <div className="hero-metrics">
          <MetricTooltip label="Margin / bu" tooltip={config.tooltips.margin_per_bushel}>
            <div className="hero-metric">
              <span className="hero-metric__value">${current.margin_per_bushel.toFixed(3)}</span>
            </div>
          </MetricTooltip>
          <MetricTooltip label="Margin / gal" tooltip={config.tooltips.margin_per_gallon}>
            <div className="hero-metric">
              <span className="hero-metric__value">${current.margin_per_gallon.toFixed(3)}</span>
            </div>
          </MetricTooltip>
          <MetricTooltip label="Z-score" tooltip={config.tooltips.z_score}>
            <div className="hero-metric">
              <span className="hero-metric__value">
                {current.z_score == null ? '—' : current.z_score.toFixed(2)}
              </span>
            </div>
          </MetricTooltip>
          <MetricTooltip label="Signal" tooltip={config.tooltips.signal_label}>
            <div className="hero-metric">
              <span className={signalClass}>{current.signal_label}</span>
            </div>
          </MetricTooltip>
        </div>
      )}

      <TimeSeriesChart
        title="Margin per bushel"
        series={margins.series}
        yKeys={['margin_per_bushel']}
        labels={['$/bu']}
        colors={['#5b9cf5']}
        valueFormatter={(value) => `$${value?.toFixed(2)}`}
        events={buildReleaseEvents(eiaReleases)}
      />
    </section>
  )
}
