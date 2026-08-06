/**
 * AnswerViz — inline SVG micro-charts for each preset question answer.
 *
 * Three visualisations, zero library dependencies:
 *   eia_interpretation  → dual sparklines: ethanol stocks + production (4–8 weekly points)
 *   cot_interpretation  → horizontal bar pair (MM net vs producer net) + percentile gauge
 *   margin_drivers      → pct-change slope bars for corn / ethanol / nat gas
 *
 * All SVG is inline and self-contained. Sizing is fixed-width so the chart
 * always fits the 260px right column without any layout math.
 */
export function AnswerViz({ questionId, chartData }) {
  if (!chartData) return null

  if (questionId === 'eia_interpretation') {
    return <EiaSparklines data={chartData} />
  }
  if (questionId === 'cot_interpretation') {
    return <CotBars data={chartData} />
  }
  if (questionId === 'margin_drivers') {
    return <MarginDriverBars data={chartData} />
  }
  return null
}

// ─────────────────────────────────────────────────────────────────────────────
// EIA: dual sparklines — stocks (blue) + production (orange)
// ─────────────────────────────────────────────────────────────────────────────

function EiaSparklines({ data }) {
  const releases = data?.eia_weekly_releases ?? []
  if (releases.length < 2) return null

  const W = 260
  const H = 90
  const PAD = { top: 12, right: 8, bottom: 20, left: 8 }
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  // Two series
  const stocks = releases.map((r) => r.stocks_mmbbl).filter((v) => v != null)
  const prods  = releases.map((r) => r.production_mbpd).filter((v) => v != null)

  function sparkPath(values, color, yMin, yMax) {
    const n = values.length
    const ys = values.map((v) =>
      yMax === yMin ? innerH / 2 : innerH - ((v - yMin) / (yMax - yMin)) * innerH,
    )
    const xs = values.map((_, i) => (i / (n - 1)) * innerW)
    const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ')
    return (
      <g>
        <path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
        {/* dots */}
        {xs.map((x, i) => (
          <circle key={i} cx={x.toFixed(1)} cy={ys[i].toFixed(1)} r="2.5" fill={color} />
        ))}
      </g>
    )
  }

  const stocksMin = Math.min(...stocks) * 0.98
  const stocksMax = Math.max(...stocks) * 1.02
  const prodsMin  = Math.min(...prods) * 0.98
  const prodsMax  = Math.max(...prods) * 1.02

  // Draw on separate normalised y-axes (both 0..innerH range)
  const stockPts  = stocks.map((v, i) => ({
    x: (i / (stocks.length - 1)) * innerW,
    y: stocksMax === stocksMin ? innerH / 2 : innerH - ((v - stocksMin) / (stocksMax - stocksMin)) * innerH,
  }))
  const prodPts   = prods.map((v, i) => ({
    x: (i / (prods.length - 1)) * innerW,
    y: prodsMax === prodsMin ? innerH / 2 : innerH - ((v - prodsMin) / (prodsMax - prodsMin)) * innerH,
  }))

  const toPath = (pts) =>
    pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')

  const latestStocks = stocks[stocks.length - 1]
  const latestProd   = prods[prods.length - 1]

  return (
    <div className="answer-viz">
      <div className="answer-viz__legend">
        <LegendDot color="#5b9cf5" label={`Stocks ${latestStocks?.toFixed(1)} MMbbl`} />
        <LegendDot color="#f0a878" label={`Prod ${latestProd?.toFixed(0)} Mbpd`} />
      </div>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="answer-viz__svg">
        <g transform={`translate(${PAD.left},${PAD.top})`}>
          {/* zero baseline */}
          <line x1={0} y1={innerH} x2={innerW} y2={innerH} stroke="#2a3140" strokeWidth="1" />
          {/* stocks sparkline */}
          <path
            d={toPath(stockPts)}
            fill="none" stroke="#5b9cf5" strokeWidth="1.8" strokeLinejoin="round"
          />
          {stockPts.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r="2.5" fill="#5b9cf5" />
          ))}
          {/* production sparkline */}
          <path
            d={toPath(prodPts)}
            fill="none" stroke="#f0a878" strokeWidth="1.8" strokeLinejoin="round"
          />
          {prodPts.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r="2.5" fill="#f0a878" />
          ))}
          {/* date labels on first and last */}
          {releases.length > 0 && (
            <>
              <text x={0} y={innerH + 14} fontSize="9" fill="#57606a" textAnchor="start">
                {releases[0].date?.slice(5)}
              </text>
              <text x={innerW} y={innerH + 14} fontSize="9" fill="#57606a" textAnchor="end">
                {releases[releases.length - 1].date?.slice(5)}
              </text>
            </>
          )}
        </g>
      </svg>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COT: horizontal bars + percentile gauge
// ─────────────────────────────────────────────────────────────────────────────

function CotBars({ data }) {
  const latest = data?.latest_cot
  const history = data?.recent_mm_net_4w ?? []
  if (!latest) return null

  const mmNet  = latest.managed_money_net_contracts ?? 0
  const prodNet = latest.producer_net_contracts ?? 0
  const pct    = latest.mm_net_percentile_5y   // 0..1

  const W = 260
  const barMax = Math.max(Math.abs(mmNet), Math.abs(prodNet), 1)
  const BAR_W = 200  // max bar width in px
  const barLen = (v) => (Math.abs(v) / barMax) * BAR_W
  const mmColor  = mmNet  >= 0 ? '#3dd68c' : '#f07178'
  const pdColor  = prodNet >= 0 ? '#3dd68c' : '#f07178'

  // Mini sparkline of recent MM net (4w)
  const nets = history.map((r) => r.mm_net).filter((v) => v != null)
  const sparkH = 36
  const sparkW = W - 16
  let sparkPath = ''
  if (nets.length >= 2) {
    const min = Math.min(...nets)
    const max = Math.max(...nets)
    const range = max - min || 1
    const pts = nets.map((v, i) => ({
      x: (i / (nets.length - 1)) * sparkW,
      y: sparkH - ((v - min) / range) * sparkH,
    }))
    sparkPath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  }

  return (
    <div className="answer-viz">
      {/* Horizontal bar: MM net */}
      <div className="answer-viz__bar-row">
        <span className="answer-viz__bar-label">MM net</span>
        <svg width={BAR_W + 60} height={16} style={{ overflow: 'visible' }}>
          <rect x={0} y={3} width={barLen(mmNet)} height={10} fill={mmColor} rx="2" />
          <text x={barLen(mmNet) + 4} y={12} fontSize="9" fill="#9aa5b1">
            {mmNet > 0 ? '+' : ''}{(mmNet / 1000).toFixed(0)}k
          </text>
        </svg>
      </div>
      {/* Horizontal bar: producer net */}
      <div className="answer-viz__bar-row">
        <span className="answer-viz__bar-label">Prod net</span>
        <svg width={BAR_W + 60} height={16} style={{ overflow: 'visible' }}>
          <rect x={0} y={3} width={barLen(prodNet)} height={10} fill={pdColor} rx="2" />
          <text x={barLen(prodNet) + 4} y={12} fontSize="9" fill="#9aa5b1">
            {prodNet > 0 ? '+' : ''}{(prodNet / 1000).toFixed(0)}k
          </text>
        </svg>
      </div>
      {/* Percentile gauge */}
      {pct != null && (
        <div className="answer-viz__gauge-row">
          <span className="answer-viz__bar-label">5Y pct</span>
          <svg width={BAR_W} height={14}>
            <rect x={0} y={4} width={BAR_W} height={6} fill="#1a2030" rx="3" />
            <rect x={0} y={4} width={pct * BAR_W} height={6}
              fill={pct > 0.8 ? '#f07178' : pct < 0.2 ? '#3dd68c' : '#5b9cf5'} rx="3" />
            <circle cx={pct * BAR_W} cy={7} r="4" fill="#fff" stroke="#242b38" strokeWidth="1" />
          </svg>
          <span className="answer-viz__gauge-label">{(pct * 100).toFixed(0)}th</span>
        </div>
      )}
      {/* 4-week MM net sparkline */}
      {sparkPath && (
        <svg width={W - 16} height={sparkH + 4} className="answer-viz__svg" style={{ marginTop: '6px' }}>
          <path d={sparkPath} fill="none" stroke="#5b9cf5" strokeWidth="1.5" strokeLinejoin="round" />
          <line x1={0} y1={sparkH} x2={sparkW} y2={sparkH} stroke="#2a3140" strokeWidth="1" />
        </svg>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Margin drivers: pct-change bars for each price leg
// ─────────────────────────────────────────────────────────────────────────────

function MarginDriverBars({ data }) {
  const trend = data?.recent_price_trend ?? []
  if (trend.length < 2) return null

  const first = trend[0]
  const last  = trend[trend.length - 1]

  const legs = [
    { key: 'corn_usd_per_bushel',    label: 'Corn',    color: '#f0a878' },
    { key: 'ethanol_usd_per_gallon', label: 'Ethanol', color: '#3dd68c' },
    { key: 'nat_gas_usd_per_mmbtu',  label: 'Nat Gas', color: '#9aa5b1' },
  ]

  // Compute pct change from first to last available value
  const changes = legs.map(({ key, label, color }) => {
    const v0 = first[key]
    const v1 = last[key]
    if (v0 == null || v1 == null || v0 === 0) return { label, color, pct: null }
    return { label, color, pct: (v1 - v0) / Math.abs(v0) }
  })

  const maxAbs = Math.max(...changes.map((c) => Math.abs(c.pct ?? 0)), 0.001)
  const BAR_HALF = 100  // px either side of zero

  return (
    <div className="answer-viz">
      <div className="answer-viz__bar-label" style={{ marginBottom: '6px', fontSize: '9px', color: '#57606a' }}>
        4-week price change
      </div>
      <svg width={260} height={changes.length * 22 + 4} viewBox={`0 0 260 ${changes.length * 22 + 4}`}>
        {/* zero line */}
        <line x1={BAR_HALF + 8} y1={0} x2={BAR_HALF + 8} y2={changes.length * 22} stroke="#2a3140" strokeWidth="1" />
        {changes.map(({ label, color, pct }, i) => {
          const y = i * 22 + 2
          if (pct == null) return null
          const barW = (Math.abs(pct) / maxAbs) * BAR_HALF
          const positive = pct >= 0
          const barX = positive ? BAR_HALF + 8 : BAR_HALF + 8 - barW
          const sign = positive ? '+' : ''
          return (
            <g key={label}>
              <text x={BAR_HALF + 4} y={y + 11} fontSize="9" fill="#7d8da6" textAnchor="end">
                {label}
              </text>
              <rect x={barX} y={y + 3} width={barW} height={10} fill={color} rx="2" />
              <text
                x={positive ? barX + barW + 3 : barX - 3}
                y={y + 12}
                fontSize="9"
                fill="#9aa5b1"
                textAnchor={positive ? 'start' : 'end'}
              >
                {sign}{(pct * 100).toFixed(1)}%
              </text>
            </g>
          )
        })}
      </svg>
      <div className="answer-viz__legend" style={{ marginTop: '2px' }}>
        <span className="answer-viz__date-range">
          {first.date?.slice(5)} → {last.date?.slice(5)}
        </span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

function LegendDot({ color, label }) {
  return (
    <span className="answer-viz__legend-item">
      <svg width="8" height="8" viewBox="0 0 8 8" style={{ display: 'inline', verticalAlign: 'middle' }}>
        <circle cx="4" cy="4" r="3.5" fill={color} />
      </svg>
      {label}
    </span>
  )
}
