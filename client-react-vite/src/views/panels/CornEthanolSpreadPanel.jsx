import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 3 — Simple ethanol/corn spread (2.8 × ethanol − corn).
 *
 * Two-leg market screen for the feedstock-vs-output relationship. This is
 * NOT the CME/CBOT-listed corn-for-ethanol crush contract; do not call it
 * that. Coproducts, operating costs, and the D6 RIN regulatory value are
 * all excluded.
 */
export function CornEthanolSpreadPanel({ spread, config }) {
  if (!spread) {
    return <section className="panel">Loading spread…</section>
  }

  const current = spread.current
  const signalClass = current ? `signal signal--${current.signal_label}` : 'signal'

  return (
    <section className="panel panel--hero">
      <header className="panel__header">
        <MetricTooltip label="Simple Ethanol/Corn Spread" tooltip={config.tooltips.spread}>
          <h2>Simple Ethanol/Corn Spread</h2>
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
        title="Simple ethanol/corn spread ($/bu of corn)"
        series={spread.series}
        yKeys={['crush_spread_usd_per_bushel']}
        labels={['Spread']}
        colors={['#c792ea']}
        valueFormatter={(value) => `$${value?.toFixed(2)}`}
      />
    </section>
  )
}
