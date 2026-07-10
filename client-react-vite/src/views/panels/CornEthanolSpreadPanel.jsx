import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 3 — CME-standard ethanol crush spread (2.8 × ethanol − corn).
 */
export function CornEthanolSpreadPanel({ spread, config }) {
  if (!spread) {
    return <section className="panel">Loading crush spread…</section>
  }

  const current = spread.current
  const signalClass = current ? `signal signal--${current.signal_label}` : 'signal'

  return (
    <section className="panel">
      <header className="panel__header">
        <MetricTooltip label="CME Ethanol Crush Spread" tooltip={config.tooltips.spread}>
          <h2>CME Ethanol Crush Spread</h2>
        </MetricTooltip>
        <span className="panel__meta">2.8 × ethanol $/gal − corn $/bu</span>
      </header>

      {current && (
        <div className="hero-metrics">
          <MetricTooltip label="Spread" tooltip={config.tooltips.spread}>
            <div className="hero-metric">
              <span className="hero-metric__value">
                ${current.crush_spread_usd_per_bushel.toFixed(2)}
              </span>
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
