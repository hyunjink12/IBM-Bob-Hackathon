import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

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

    const xValues = series.map((point) => Math.floor(new Date(point[xKey]).getTime() / 1000))
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
            values: (_, ticks) =>
              ticks.map((value) => {
                const date = new Date(value * 1000)
                return `${date.getMonth() + 1}/${date.getDate()}`
              }),
          },
          {
            stroke: '#9aa5b1',
            grid: { stroke: '#2a3140' },
            values: (_, ticks) => ticks.map((value) => valueFormatter(value)),
          },
        ],
        scales: { x: { time: true } },
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
