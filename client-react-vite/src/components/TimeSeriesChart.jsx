import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

/** Compact M/D/YY label for chart x-axis ticks. */
function formatChartAxisDate(unixSeconds) {
  const date = new Date(unixSeconds * 1000)
  const year = String(date.getFullYear()).slice(-2)
  return `${date.getMonth() + 1}/${date.getDate()}/${year}`
}

/**
 * Read a CSS custom property from :root at call time. uPlot needs concrete
 * color strings (it draws to canvas, doesn't inherit CSS), so we resolve
 * theme tokens up-front instead of passing var() references through.
 */
function readCssVar(name, fallback) {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/**
 * Track the active `data-theme` on <html> and trigger a re-render whenever
 * it changes. The chart useEffect keys on the returned string so uPlot
 * fully re-inits with fresh theme colors on toggle.
 */
function useThemeVersion() {
  const [theme, setTheme] = useState(() =>
    typeof document !== 'undefined' ? document.documentElement.dataset.theme || 'dark' : 'dark',
  )
  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return undefined
    const observer = new MutationObserver(() => {
      setTheme(document.documentElement.dataset.theme || 'dark')
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])
  return theme
}

/**
 * Resolve a caller-supplied series color. Passing the sentinel `'accent'`
 * (from a panel that wants to track the theme) returns the current
 * --accent token; any hex or rgba() passes through untouched.
 */
function resolveSeriesColor(color) {
  if (color === 'accent') return readCssVar('--accent', '#4589ff')
  return color
}

/**
 * Convert an incoming date value to Unix seconds anchored at LOCAL midnight.
 *
 * Backend sends date-only ISO strings ("2026-07-30"). `new Date("2026-07-30")`
 * parses as midnight UTC, which shows as 8pm the previous day in EDT and
 * misaligns axis ticks and tooltips by one day. Parsing the components as
 * local time keeps daily observations on their real calendar day.
 */
function toUnixSecondsLocal(value) {
  if (value instanceof Date) return Math.floor(value.getTime() / 1000)
  const s = String(value)
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (dateOnly) {
    const [, y, m, d] = dateOnly
    return Math.floor(new Date(Number(y), Number(m) - 1, Number(d)).getTime() / 1000)
  }
  return Math.floor(new Date(s).getTime() / 1000)
}

/**
 * Lightweight time-series chart wrapper around uPlot.
 *
 * Optional `events` overlays marker dots at specific dates with a rich hover
 * popup — used for EIA weekly release annotations on the margin chart.
 * Each event: { date, tooltip: { title, rows: [{label, value, delta?}] } }
 */
export function TimeSeriesChart({
  title,
  series,
  xKey = 'date',
  yKeys,
  labels,
  colors,
  height = 260,
  valueFormatter = (value) => value?.toFixed(2),
  events,
  eventPrimaryKey,
}) {
  const containerRef = useRef(null)
  const plotRef = useRef(null)
  const eventsByXRef = useRef(new Map())
  const [hoverPopup, setHoverPopup] = useState(null)
  const theme = useThemeVersion()

  useEffect(() => {
    if (!containerRef.current || !series?.length) {
      return undefined
    }

    // Read theme tokens fresh on every init — grid + axis + accent all track
    // the active theme. The uPlot canvas doesn't inherit CSS, so we have to
    // resolve concrete color strings up-front.
    const gridStroke = readCssVar('--border-subtle', '#1f242c')
    const axisStroke = readCssVar('--text-secondary', '#8a929c')
    const accentColor = readCssVar('--accent', '#4589ff')
    const pageBg = readCssVar('--bg-page', '#0a0c0f')
    const resolvedSeriesColors = colors.map(resolveSeriesColor)

    const xValues = series.map((point) => toUnixSecondsLocal(point[xKey]))
    const primaryKey = eventPrimaryKey ?? yKeys[0]
    const primaryByX = new Map(
      xValues.map((x, i) => [x, series[i][primaryKey] ?? null]),
    )

    // Build the event marker series aligned to main x-axis. Only emit a y at
    // dates that both have an event AND a primary value to sit on top of.
    const eventXSet = new Set(
      (events ?? [])
        .map((e) => toUnixSecondsLocal(e.date))
        .filter((x) => primaryByX.has(x)),
    )
    const eventYValues = xValues.map((x) =>
      eventXSet.has(x) ? primaryByX.get(x) : null,
    )

    // Fast lookup on hover.
    eventsByXRef.current = new Map(
      (events ?? [])
        .map((e) => [toUnixSecondsLocal(e.date), e])
        .filter(([x]) => primaryByX.has(x)),
    )

    const data = [
      xValues,
      ...yKeys.map((key) => series.map((point) => point[key] ?? null)),
      ...(events ? [eventYValues] : []),
    ]

    const plot = new uPlot(
      {
        width: containerRef.current.clientWidth,
        height,
        title,
        series: [
          {},
          ...yKeys.map((_, index) => ({
            label: labels[index],
            stroke: resolvedSeriesColors[index],
            width: 2,
            points: { show: false },
          })),
          ...(events
            ? [
                {
                  label: 'EIA release',
                  stroke: accentColor,
                  fill: accentColor,
                  width: 0,
                  paths: () => null,
                  points: {
                    show: true,
                    size: 7,
                    // Marker outline uses the page background so the dot
                    // pops against both dark and light chart canvases.
                    stroke: pageBg,
                    fill: accentColor,
                  },
                },
              ]
            : []),
        ],
        axes: [
          {
            stroke: axisStroke,
            grid: { stroke: gridStroke, width: 1 },
            ticks: { stroke: gridStroke, width: 1 },
            values: (_, ticks) => ticks.map(formatChartAxisDate),
          },
          {
            stroke: axisStroke,
            grid: { stroke: gridStroke, width: 1 },
            ticks: { stroke: gridStroke, width: 1 },
            values: (_, ticks) => ticks.map((value) => valueFormatter(value)),
          },
        ],
        scales: { x: { time: true } },
        cursor: {
          drag: { x: true, y: false, setScale: true },
        },
        hooks: {
          setCursor: [
            (u) => {
              if (!events?.length) return
              const idx = u.cursor.idx
              if (idx == null) {
                setHoverPopup(null)
                return
              }
              const x = u.data[0][idx]
              const event = eventsByXRef.current.get(x)
              if (!event) {
                setHoverPopup(null)
                return
              }
              const y = primaryByX.get(x)
              if (y == null) return
              const left = u.valToPos(x, 'x')
              const top = u.valToPos(y, u.series[1].scale ?? 'y')
              // Flip popup to the left of the marker when there isn't ~260px
              // of room to the right; otherwise the containing block clips it.
              const flipX = left > u.over.clientWidth - 260
              setHoverPopup({ left, top, event, flipX })
            },
          ],
        },
      },
      data,
      containerRef.current,
    )

    plotRef.current = plot

    const handleResize = () => {
      plot.setSize({
        width: containerRef.current.clientWidth,
        height,
      })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      plot.destroy()
      plotRef.current = null
      setHoverPopup(null)
    }
  }, [series, xKey, yKeys, labels, colors, height, title, valueFormatter, events, eventPrimaryKey, theme])

  return (
    <div className="chart-shell" ref={containerRef} style={{ position: 'relative' }}>
      {hoverPopup ? (
        <EventPopup
          left={hoverPopup.left}
          top={hoverPopup.top}
          event={hoverPopup.event}
          flipX={hoverPopup.flipX}
        />
      ) : null}
    </div>
  )
}

function EventPopup({ left, top, event, flipX }) {
  const tooltip = event.tooltip ?? {}
  // Nudge slightly up-and-away from the point. When flipX, anchor to the
  // right of the marker instead of the left so we don't get clipped or
  // squeezed by the containing block near the chart's right edge.
  const offsetX = 12
  const offsetY = -8
  return (
    <div
      className="chart-event-popup"
      style={{
        position: 'absolute',
        left: `${flipX ? left - offsetX : left + offsetX}px`,
        top: `${top + offsetY}px`,
        transform: flipX ? 'translate(-100%, -100%)' : 'translate(0, -100%)',
      }}
    >
      {tooltip.title ? (
        <div className="chart-event-popup__title">{tooltip.title}</div>
      ) : null}
      {(tooltip.rows ?? []).map((row) => (
        <div key={row.label} className="chart-event-popup__row">
          <span className="chart-event-popup__label">{row.label}</span>
          <span className="chart-event-popup__value">
            {row.value}
            {row.delta ? (
              <span
                className={`chart-event-popup__delta chart-event-popup__delta--${row.deltaDirection ?? 'flat'}`}
              >
                {row.delta}
              </span>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  )
}
