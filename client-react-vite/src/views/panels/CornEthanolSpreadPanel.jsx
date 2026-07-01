import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 3 — net ethanol value vs corn spread.
 */
export function CornEthanolSpreadPanel({ spread, config }) {
  if (!spread) {
    return <section className="panel">Loading corn vs ethanol spread…</section>
  }

  return (
    <section className="panel">
      <header className="panel__header">
        <MetricTooltip label="Corn vs Ethanol Spread" tooltip={config.tooltips.spread}>
          <h2>Corn vs Ethanol Spread</h2>
        </MetricTooltip>
        <span className="panel__meta">Net ethanol $/bu − corn $/bu</span>
      </header>
      <TimeSeriesChart
        title="Spread ($/bu)"
        series={spread.series}
        yKeys={['spread_usd_per_bushel']}
        labels={['Spread']}
        colors={['#c792ea']}
        valueFormatter={(value) => `$${value?.toFixed(2)}`}
      />
    </section>
  )
}
