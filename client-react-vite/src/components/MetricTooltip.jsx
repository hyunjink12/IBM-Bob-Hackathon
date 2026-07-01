/**
 * Subtle on-hover tooltip for key metrics.
 */
export function MetricTooltip({ label, tooltip, children }) {
  return (
    <span className="metric-tooltip" tabIndex={0}>
      <span className="metric-tooltip__label">{label}</span>
      <span className="metric-tooltip__popup" role="tooltip">
        {tooltip}
      </span>
      {children}
    </span>
  )
}
