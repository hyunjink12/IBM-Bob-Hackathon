import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

/** Compact M/D/YY label for chart x-axis ticks. */
function formatChartAxisDate(unixSeconds) {
  const date = new Date(unixSeconds * 1000)
  const year = String(date.getFullYear()).slice(-2)
  return `${date.getMonth() + 1}/${date.getDate()}/${year}`
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
}) {
  const containerRef = useRef(null)
  const plotRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !series?.length) {
      return undefined
    }

    const xValues = series.map((point) => toUnixSecondsLocal(point[xKey]))
    const data = [
      xValues,
      ...yKeys.map((key) => series.map((point) => point[key] ?? null)),
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
            stroke: colors[index],
            width: 2,
          })),
        ],
        axes: [
          {
            stroke: '#9aa5b1',
            grid: { stroke: '#2a3140' },
            values: (_, ticks) => ticks.map(formatChartAxisDate),
          },
          {
            stroke: '#9aa5b1',
            grid: { stroke: '#2a3140' },
            values: (_, ticks) => ticks.map((value) => valueFormatter(value)),
          },
        ],
        scales: { x: { time: true } },
        cursor: {
          drag: { x: true, y: false, setScale: true },
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
    }
  }, [series, xKey, yKeys, labels, colors, height, title, valueFormatter])

  return <div className="chart-shell" ref={containerRef} />
}
