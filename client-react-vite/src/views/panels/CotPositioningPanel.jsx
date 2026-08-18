import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'
import { ChartControls } from '../ChartControls.jsx'

// COT is a weekly series. 1W → 1 point, 1M → ~4 points; both are useless for
// positioning context, so they're excluded from this panel's range dropdown.
// Everything else stays available (3M gives ~13 points, plenty).
const COT_ALLOWED_RANGES = ['3M', '6M', 'YTD', '1Y', '2Y', '5Y', 'ALL']

/**
 * Panel — CBOT Corn managed-money positioning.
 *
 * Casual: where are the specs sitting, and how stretched is that?
 *
 * MM net (long − short) is the directional signal. 5Y empirical percentile
 * says whether the current print is historically stretched or benign.
 */
export function CotPositioningPanel({
  cotPositioning,
  config,
  chartRange,
  onChartRangeChange,
}) {
  if (!cotPositioning) {
    return <section className="panel">Loading COT positioning…</section>
  }

  const current = cotPositioning.current
  const series = cotPositioning.series ?? []

  if (!current) {
    return (
      <section className="panel panel--hero">
        <header className="panel__header">
          <h2>CBOT Corn — Managed Money Positioning</h2>
        </header>
        <p className="empty-state">
          No CFTC COT data yet. First ingestion run after the next Friday 3:30 PM ET
          release will populate this panel.
        </p>
      </section>
    )
  }

  const percentileLabel = current.mm_net_percentile_5y != null
    ? formatPercentile(current.mm_net_percentile_5y)
    : { value: '—', label: '' }

  return (
    <section className="panel panel--hero">
      <header className="panel__header">
        <h2>CBOT Corn — Managed Money Positioning</h2>
        <div className="panel__header-right">
          <span className="panel__meta">
            As of {current.report_date} · CFTC Disaggregated futures-only
          </span>
          {config && onChartRangeChange ? (
            <ChartControls
              config={config}
              scopeId="cot"
              chartRange={chartRange}
              onChartRangeChange={onChartRangeChange}
              chartRanges={COT_ALLOWED_RANGES}
            />
          ) : null}
        </div>
      </header>

      <div className="hero-metrics">
        <div className="hero-metric">
          <span className="hero-metric__value">
            {formatSignedThousands(current.managed_money_net)}
          </span>
        </div>
        <div className="hero-metric">
          <span className="hero-metric__value">
            {formatSignedThousands(current.managed_money_net_wow, { withPlus: true })}
          </span>
        </div>
        <div className="hero-metric">
          <span className="hero-metric__value">{percentileLabel.value}</span>
        </div>
        <div className="hero-metric">
          <span className="hero-metric__value">
            {formatThousands(current.open_interest)}
          </span>
        </div>
      </div>

      <div className="hero-metric-labels">
        <span>MM Net</span>
        <span>WoW Δ</span>
        <span>5Y %ile{percentileLabel.label ? ` · ${percentileLabel.label}` : ''}</span>
        <span>Open Interest</span>
      </div>

      <TimeSeriesChart
        title="Managed money net position (contracts, long − short)"
        series={series}
        yKeys={['managed_money_net']}
        labels={['MM net']}
        colors={['accent']}
        valueFormatter={(value) =>
          value == null ? '—' : `${Math.round(value / 1000).toLocaleString()}k`
        }
        events={buildCotEvents(series)}
      />

      <p className="panel__legend">
        <span className="panel__legend-swatch panel__legend-swatch--bull" /> bullish for corn
        <span className="panel__legend-swatch panel__legend-swatch--bear" /> bearish for corn
        <span className="panel__legend-note">— colored by price impact, not arithmetic sign.</span>
      </p>
    </section>
  )
}

/**
 * Turn each COT weekly report into a hover-event on the chart so traders
 * see the full disaggregated breakdown at every Friday print, not just the
 * MM-net line value.
 */
function buildCotEvents(series) {
  if (!series?.length) return undefined
  return series.map((r) => ({
    date: r.date,
    tooltip: {
      title: `CFTC · ${formatReleaseDate(r.date)}`,
      rows: [
        {
          label: 'MM Long',
          value: formatSignedThousands(r.managed_money_long),
          delta: formatSignedThousands(r.managed_money_long_wow, { withPlus: true }),
          deltaDirection: deltaDirection(r.managed_money_long_wow),
        },
        {
          label: 'MM Short',
          value: formatSignedThousands(r.managed_money_short),
          delta: formatSignedThousands(r.managed_money_short_wow, { withPlus: true }),
          // For shorts, "up" (increasing short) is bearish → red; flip.
          deltaDirection: invertDirection(deltaDirection(r.managed_money_short_wow)),
        },
        {
          label: 'MM Net',
          value: formatSignedThousands(r.managed_money_net),
          delta: formatSignedThousands(r.managed_money_net_wow, { withPlus: true }),
          deltaDirection: deltaDirection(r.managed_money_net_wow),
        },
        {
          label: 'Producer Net',
          value: formatSignedThousands(r.producer_net),
        },
        {
          label: 'Open Interest',
          value: formatThousands(r.open_interest),
          delta: formatSignedThousands(r.open_interest_wow, { withPlus: true }),
          deltaDirection: 'flat',
        },
      ],
    },
  }))
}

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

function deltaDirection(value) {
  if (value == null || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

function invertDirection(d) {
  if (d === 'up') return 'down'
  if (d === 'down') return 'up'
  return d
}

/* ---------- formatters ---------- */

function formatSignedThousands(value, { withPlus = false } = {}) {
  if (value == null || Number.isNaN(value)) return '—'
  const rounded = Math.round(value / 1000)
  if (rounded === 0) return '0k'
  const sign = rounded > 0 ? (withPlus ? '+' : '') : ''
  return `${sign}${rounded.toLocaleString()}k`
}

function formatThousands(value) {
  if (value == null || Number.isNaN(value)) return '—'
  return Math.round(value / 1000).toLocaleString() + 'k'
}

function formatPercentile(fraction) {
  const pct = Math.round(fraction * 100)
  let label = 'balanced'
  if (pct >= 85) label = 'stretched long'
  else if (pct >= 65) label = 'long-leaning'
  else if (pct <= 15) label = 'stretched short'
  else if (pct <= 35) label = 'short-leaning'
  return { value: `${pct}${ordinalSuffix(pct)}`, label }
}

function ordinalSuffix(n) {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return s[(v - 20) % 10] || s[v] || s[0]
}
