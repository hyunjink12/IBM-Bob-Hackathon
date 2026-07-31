/**
 * Persistent range + granularity dropdowns for the tabbed chart body.
 *
 * State lives in the view-model, so switching tabs preserves both selections
 * and every chart on either tab reacts to a change from one place.
 */
export function ChartControls({
  config,
  chartRange,
  onChartRangeChange,
  chartGranularity,
  onChartGranularityChange,
  isGranularityAllowed,
}) {
  return (
    <div className="chart-controls">
      <div className="chart-controls__group">
        <label htmlFor="chart-controls-granularity">Granularity</label>
        <select
          id="chart-controls-granularity"
          value={chartGranularity}
          onChange={(event) => onChartGranularityChange(event.target.value)}
        >
          {config.granularities.map((option) => {
            const allowed = isGranularityAllowed
              ? isGranularityAllowed(option.value)
              : true
            return (
              <option
                key={option.value}
                value={option.value}
                disabled={!allowed}
                title={allowed ? undefined : 'Needs a longer range to plot enough bars'}
              >
                {allowed ? option.label : `${option.label} —`}
              </option>
            )
          })}
        </select>
      </div>
      <div className="chart-controls__group">
        <label htmlFor="chart-controls-range">Range</label>
        <select
          id="chart-controls-range"
          value={chartRange}
          onChange={(event) => onChartRangeChange(event.target.value)}
        >
          {config.chartRanges.map((range) => (
            <option key={range} value={range}>
              {range}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
