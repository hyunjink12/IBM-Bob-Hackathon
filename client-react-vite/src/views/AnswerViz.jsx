/**
 * AnswerViz — inline SVG micro-charts for each preset question answer.
 *
 * Design rules:
 *  - All geometry is fully contained within the SVG viewBox. No overflow.
 *  - SVG uses width="100%" so it scales to whatever column width it's placed in.
 *  - Animations: lines draw in via stroke-dashoffset, bars scale in via scaleX,
 *    dots/text fade in with a short delay so they appear after the path.
 *  - Zero library dependencies — pure SVG + CSS animations.
 */

// ─── Total chart width in SVG user-units. All geometry is relative to this. ──
const VW = 280

export function AnswerViz({ questionId, chartData }) {
  if (!chartData) return null
  if (questionId === 'eia_interpretation') return <EiaSparklines data={chartData} />
  if (questionId === 'cot_interpretation') return <CotBars data={chartData} />
  if (questionId === 'margin_drivers')     return <MarginDriverBars data={chartData} />
  return null
}

// ─────────────────────────────────────────────────────────────────────────────
// EIA: dual sparklines — stocks (blue) + production (orange)
// viewBox height = 110. Padding: top 14, bottom 22, left 4, right 4.
// ─────────────────────────────────────────────────────────────────────────────
function EiaSparklines({ data }) {
  const releases = data?.eia_weekly_releases ?? []
  if (releases.length < 2) return null

  const VH = 110
  const pad = { t: 14, b: 22, l: 4, r: 4 }
  const iW = VW - pad.l - pad.r
  const iH = VH - pad.t - pad.b

  const stocks = releases.map((r) => r.stocks_mmbbl).filter((v) => v != null)
  const prods  = releases.map((r) => r.production_mbpd).filter((v) => v != null)

  const pts = (values) => {
    const min = Math.min(...values) * 0.98
    const max = Math.max(...values) * 1.02
    const range = max === min ? 1 : max - min
    return values.map((v, i) => ({
      x: pad.l + (i / (values.length - 1)) * iW,
      y: pad.t + iH - ((v - min) / range) * iH,
    }))
  }

  const toD = (points) =>
    points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')

  const sPts = pts(stocks)
  const pPts = pts(prods)

  // Approximate path length for stroke-dasharray animation
  const pathLen = (points) =>
    points.slice(1).reduce((acc, p, i) => {
      const prev = points[i]
      return acc + Math.hypot(p.x - prev.x, p.y - prev.y)
    }, 0)

  const sLen = Math.ceil(pathLen(sPts)) + 10
  const pLen = Math.ceil(pathLen(pPts)) + 10

  const latestStocks = stocks[stocks.length - 1]
  const latestProd   = prods[prods.length - 1]

  const baselineY = pad.t + iH

  return (
    <div className="answer-viz">
      <div className="answer-viz__legend answer-viz--fadein">
        <LegendDot color="#5b9cf5" label={`Stocks  ${latestStocks?.toFixed(1)} MMbbl`} />
        <LegendDot color="#f0a878" label={`Prod  ${latestProd?.toFixed(0)} Mbpd`} />
      </div>
      <svg
        width="100%"
        viewBox={`0 0 ${VW} ${VH}`}
        className="answer-viz__svg"
        aria-hidden="true"
      >
        {/* baseline */}
        <line x1={pad.l} y1={baselineY} x2={pad.l + iW} y2={baselineY}
          stroke="#2a3140" strokeWidth="1" />

        {/* stocks line — draws in */}
        <path
          d={toD(sPts)}
          fill="none" stroke="#5b9cf5" strokeWidth="2" strokeLinejoin="round"
          strokeDasharray={sLen} strokeDashoffset={sLen}
          className="viz-line-anim"
        />
        {/* dots fade in after line */}
        {sPts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#5b9cf5"
            className="viz-dot-anim" style={{ animationDelay: `${0.55 + i * 0.06}s` }} />
        ))}

        {/* production line */}
        <path
          d={toD(pPts)}
          fill="none" stroke="#f0a878" strokeWidth="2" strokeLinejoin="round"
          strokeDasharray={pLen} strokeDashoffset={pLen}
          className="viz-line-anim" style={{ animationDelay: '0.1s' }}
        />
        {pPts.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="#f0a878"
            className="viz-dot-anim" style={{ animationDelay: `${0.65 + i * 0.06}s` }} />
        ))}

        {/* date labels — clamped inside viewBox */}
        <text x={pad.l} y={baselineY + 14} fontSize="9" fill="#57606a" textAnchor="start"
          className="answer-viz--fadein">
          {releases[0].date?.slice(5)}
        </text>
        <text x={pad.l + iW} y={baselineY + 14} fontSize="9" fill="#57606a" textAnchor="end"
          className="answer-viz--fadein">
          {releases[releases.length - 1].date?.slice(5)}
        </text>
      </svg>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// COT: horizontal bars + percentile gauge + 4w sparkline
// All geometry contained within VW×170 viewBox.
// Bar area: label 52px + track 180px + value 48px = 280px total.
// ─────────────────────────────────────────────────────────────────────────────
function CotBars({ data }) {
  const latest  = data?.latest_cot
  const history = data?.recent_mm_net_4w ?? []
  if (!latest) return null

  const mmNet   = latest.managed_money_net_contracts ?? 0
  const prodNet = latest.producer_net_contracts ?? 0
  const pct     = latest.mm_net_percentile_5y        // 0..1

  // Layout constants — all in SVG user-units, all ≤ VW
  const LABEL_W = 52   // label column
  const TRACK_W = 180  // bar track
  const VALUE_W = VW - LABEL_W - TRACK_W  // = 48 — value label column

  const barMax = Math.max(Math.abs(mmNet), Math.abs(prodNet), 1)
  const barPx  = (v) => (Math.abs(v) / barMax) * TRACK_W

  const mmColor  = mmNet  >= 0 ? '#3dd68c' : '#f07178'
  const pdColor  = prodNet >= 0 ? '#3dd68c' : '#f07178'

  // Sparkline geometry
  const nets  = history.map((r) => r.mm_net).filter((v) => v != null)
  const hasSpk = nets.length >= 2
  const SKH    = 40   // sparkline height in SVG units
  const SKY    = 110  // y-top of sparkline area
  const VH     = hasSpk ? SKY + SKH + 8 : 100

  let sparkD = ''
  let sparkLen = 0
  if (hasSpk) {
    const min = Math.min(...nets)
    const max = Math.max(...nets)
    const rng = max === min ? 1 : max - min
    const spkPts = nets.map((v, i) => ({
      x: (i / (nets.length - 1)) * VW,
      y: SKY + SKH - ((v - min) / rng) * SKH,
    }))
    sparkD = spkPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    sparkLen = Math.ceil(spkPts.slice(1).reduce((acc, p, i) => {
      const prev = spkPts[i]
      return acc + Math.hypot(p.x - prev.x, p.y - prev.y)
    }, 0)) + 10
  }

  const fmtK = (v) => `${v > 0 ? '+' : ''}${(v / 1000).toFixed(0)}k`

  // Helper: bar row at given y. transformOrigin trick for scaleX animation.
  function BarRow({ y, label, value, barW, color, delay }) {
    return (
      <g>
        <text x={LABEL_W - 4} y={y + 11} fontSize="9.5" fill="#7d8da6" textAnchor="end">
          {label}
        </text>
        {/* track background */}
        <rect x={LABEL_W} y={y + 3} width={TRACK_W} height={10} fill="#1a2030" rx="2" />
        {/* value bar — scaleX animates from 0→1 around its left edge */}
        <rect
          x={LABEL_W} y={y + 3} width={barW} height={10} fill={color} rx="2"
          className="viz-bar-anim"
          style={{
            transformOrigin: `${LABEL_W}px ${y + 8}px`,
            animationDelay: delay,
          }}
        />
        {/* value label — clamped to stay inside VW */}
        <text
          x={Math.min(LABEL_W + barW + 4, VW - VALUE_W + 4)}
          y={y + 12}
          fontSize="9" fill="#9aa5b1" textAnchor="start"
          className="answer-viz--fadein"
          style={{ animationDelay: delay }}
        >
          {fmtK(value)}
        </text>
      </g>
    )
  }

  return (
    <div className="answer-viz">
      <svg width="100%" viewBox={`0 0 ${VW} ${VH}`} className="answer-viz__svg" aria-hidden="true">
        {/* MM net bar */}
        <BarRow y={4}  label="MM net"   value={mmNet}   barW={barPx(mmNet)}   color={mmColor}  delay="0s" />
        {/* Producer net bar */}
        <BarRow y={28} label="Prod net" value={prodNet} barW={barPx(prodNet)} color={pdColor}  delay="0.08s" />

        {/* Percentile gauge */}
        {pct != null && (() => {
          const gaugeY = 56
          const gaugeColor = pct > 0.8 ? '#f07178' : pct < 0.2 ? '#3dd68c' : '#5b9cf5'
          const dotX = LABEL_W + pct * TRACK_W
          return (
            <g>
              <text x={LABEL_W - 4} y={gaugeY + 10} fontSize="9.5" fill="#7d8da6" textAnchor="end">5Y pct</text>
              {/* track */}
              <rect x={LABEL_W} y={gaugeY + 3} width={TRACK_W} height={6} fill="#1a2030" rx="3" />
              {/* fill — animates width */}
              <rect x={LABEL_W} y={gaugeY + 3}
                width={pct * TRACK_W} height={6} fill={gaugeColor} rx="3"
                className="viz-bar-anim"
                style={{ transformOrigin: `${LABEL_W}px ${gaugeY + 6}px`, animationDelay: '0.16s' }}
              />
              {/* dot */}
              <circle cx={dotX} cy={gaugeY + 6} r="5" fill="#e6edf3" stroke="#151922" strokeWidth="1.5"
                className="viz-dot-anim" style={{ animationDelay: '0.5s' }} />
              {/* label */}
              <text
                x={Math.min(dotX + 8, VW - 4)}
                y={gaugeY + 10}
                fontSize="9" fill="#9aa5b1" textAnchor="start"
                className="answer-viz--fadein"
                style={{ animationDelay: '0.5s' }}
              >
                {(pct * 100).toFixed(0)}th
              </text>
            </g>
          )
        })()}

        {/* 4-week MM net sparkline */}
        {hasSpk && (
          <>
            <line x1={0} y1={SKY + SKH} x2={VW} y2={SKY + SKH} stroke="#2a3140" strokeWidth="1" />
            <path d={sparkD} fill="none" stroke="#5b9cf5" strokeWidth="1.8" strokeLinejoin="round"
              strokeDasharray={sparkLen} strokeDashoffset={sparkLen}
              className="viz-line-anim" style={{ animationDelay: '0.25s' }} />
            <text x={0} y={SKY + SKH + 14} fontSize="8" fill="#57606a" className="answer-viz--fadein">
              4-week MM net trend
            </text>
          </>
        )}
      </svg>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Margin drivers: diverging bar chart, centred on zero
// Label 52 | neg bar → zero | zero → pos bar | value
// Zero line sits at x = LABEL_W + HALF_W
// ─────────────────────────────────────────────────────────────────────────────
function MarginDriverBars({ data }) {
  const trend = data?.recent_price_trend ?? []
  if (trend.length < 2) return null

  const first = trend[0]
  const last  = trend[trend.length - 1]

  const LEGS = [
    { key: 'corn_usd_per_bushel',    label: 'Corn',    color: '#f0a878' },
    { key: 'ethanol_usd_per_gallon', label: 'Ethanol', color: '#3dd68c' },
    { key: 'nat_gas_usd_per_mmbtu',  label: 'Nat Gas', color: '#9aa5b1' },
  ]

  const changes = LEGS.map(({ key, label, color }) => {
    const v0 = first[key], v1 = last[key]
    if (v0 == null || v1 == null || v0 === 0) return { label, color, pct: null }
    return { label, color, pct: (v1 - v0) / Math.abs(v0) }
  })

  const maxAbs = Math.max(...changes.map((c) => Math.abs(c.pct ?? 0)), 0.001)

  const LABEL_W = 52
  const VALUE_W = 40                     // reserved column on BOTH sides for value labels
  const GUTTER  = 6                      // gap between bar tip and value label
  const HALF_W  = (VW - LABEL_W - VALUE_W * 2) / 2   // usable bar width on each side of zero
  const ZERO_X  = LABEL_W + VALUE_W + HALF_W        // zero axis shifted right by neg-value column

  const ROW_H = 22
  const VH    = changes.length * ROW_H + 20

  return (
    <div className="answer-viz">
      <svg width="100%" viewBox={`0 0 ${VW} ${VH}`} className="answer-viz__svg" aria-hidden="true">
        {/* zero axis */}
        <line x1={ZERO_X} y1={0} x2={ZERO_X} y2={VH - 16} stroke="#2a3140" strokeWidth="1" />

        {changes.map(({ label, color, pct }, i) => {
          const y    = i * ROW_H + 2
          if (pct == null) return null
          const barW = (Math.abs(pct) / maxAbs) * HALF_W
          const pos  = pct >= 0
          const barX = pos ? ZERO_X : ZERO_X - barW
          const sign = pos ? '+' : ''

          // Value label always sits just past the bar tip on the outside so
          // it can't be obscured by the bar fill. Zero-length bars fall back
          // to sitting flush with the axis rather than floating in space.
          const valX = pos
            ? ZERO_X + Math.max(barW, 0) + GUTTER
            : ZERO_X - Math.max(barW, 0) - GUTTER
          const valAnchor = pos ? 'start' : 'end'

          return (
            <g key={label}>
              <text x={LABEL_W - 4} y={y + 12} fontSize="9.5" fill="#7d8da6" textAnchor="end">
                {label}
              </text>
              <rect
                x={barX} y={y + 3} width={barW} height={10} fill={color} rx="2"
                className="viz-bar-anim"
                style={{
                  transformOrigin: `${ZERO_X}px ${y + 8}px`,
                  animationDelay: `${i * 0.07}s`,
                }}
              />
              <text
                x={valX} y={y + 12} fontSize="9" fill="#9aa5b1" textAnchor={valAnchor}
                className="answer-viz--fadein"
                style={{ animationDelay: `${0.35 + i * 0.07}s` }}
              >
                {sign}{(pct * 100).toFixed(1)}%
              </text>
            </g>
          )
        })}

        {/* date range label — bottom, full width */}
        <text x={VW / 2} y={VH - 4} fontSize="8" fill="#57606a" textAnchor="middle"
          className="answer-viz--fadein">
          {first.date?.slice(5)} → {last.date?.slice(5)}
        </text>
      </svg>
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
