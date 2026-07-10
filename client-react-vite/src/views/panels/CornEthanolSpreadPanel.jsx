import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 3 — CME-standard ethanol crush spread (2.8 × ethanol − corn).
 */
export function CornEthanolSpreadPanel({ spread, config }) {
  if (!spread) {
    return <section className="panel">Loading crush spread…</section>
  }

  return (
    <section className="panel">
      <header className="panel__header">
        <MetricTooltip label="CME Ethanol Crush Spread" tooltip={config.tooltips.spread}>
          <h2>CME Ethanol Crush Spread</h2>
        </MetricTooltip>
        <span className="panel__meta">2.8 × ethanol $/gal − corn $/bu</span>
      </header>
      <TimeSeriesChart
        title="Crush spread ($/bu of corn)"
        series={spread.series}
        yKeys={['crush_spread_usd_per_bushel']}
        labels={['Crush spread']}
        colors={['#c792ea']}
        valueFormatter={(value) => `$${value?.toFixed(2)}`}
      />
    </section>
  )
}
