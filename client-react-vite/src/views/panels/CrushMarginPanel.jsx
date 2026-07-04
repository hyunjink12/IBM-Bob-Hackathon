import { MetricTooltip } from '../../components/MetricTooltip.jsx'
import { TimeSeriesChart } from '../../components/TimeSeriesChart.jsx'

/**
 * Panel 2 — crush margin centerpiece with z-score and signal label.
 */
export function CrushMarginPanel({ margins, config }) {
  if (!margins) {
    return <section className="panel">Loading crush margin…</section>
  }

  const current = margins.current
  const signalClass = current ? `signal signal--${current.signal_label}` : 'signal'

  return (
    <section className="panel panel--hero">
      <header className="panel__header">
        <h2>Ethanol Crush Margin</h2>
        <span className="panel__meta">Range: {margins.range}</span>
      </header>

      {current && (
        <div className="hero-metrics">
          <MetricTooltip label="Margin / bu" tooltip={config.tooltips.margin_per_bushel}>
            <div className="hero-metric">
              <span className="hero-metric__value">${current.margin_per_bushel.toFixed(3)}</span>
            </div>
          </MetricTooltip>
          <MetricTooltip label="Margin / gal" tooltip={config.tooltips.margin_per_gallon}>
            <div className="hero-metric">
              <span className="hero-metric__value">${current.margin_per_gallon.toFixed(3)}</span>
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
        title="Margin per bushel"
        series={margins.series}
        yKeys={['margin_per_bushel']}
        labels={['$/bu']}
        colors={['#5b9cf5']}
        valueFormatter={(value) => `$${value?.toFixed(2)}`}
      />
    </section>
  )
}
