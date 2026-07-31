/**
 * Range + granularity dropdowns for one chart scope.
 *
 * Both dropdowns operate independently — picking a short range doesn't
 * mutate granularity, and picking a coarse granularity doesn't mutate
 * range. If a combination yields one bar, that's the user's intent.
 *
 * `scopeId` namespaces the <select> ids so multiple ChartControls can
 * coexist on the page (e.g. shared top toolbar + a COT-specific one).
 */
export function ChartControls({
  config,
  scopeId = 'shared',
  chartRange,
  onChartRangeChange,
  chartGranularity,
  onChartGranularityChange,
  chartRanges,
}) {
  const showGranularity = Boolean(onChartGranularityChange)
  const rangesToShow = chartRanges ?? config.chartRanges
  return (
    <div className="chart-controls">
      {showGranularity ? (
        <div className="chart-controls__group">
          <label htmlFor={`chart-controls-granularity-${scopeId}`}>Granularity</label>
          <select
            id={`chart-controls-granularity-${scopeId}`}
            className="chart-controls__select chart-controls__select--granularity"
            value={chartGranularity}
            onChange={(event) => onChartGranularityChange(event.target.value)}
          >
            {config.granularities.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="chart-controls__group">
        <label htmlFor={`chart-controls-range-${scopeId}`}>Range</label>
        <select
          id={`chart-controls-range-${scopeId}`}
          className="chart-controls__select chart-controls__select--range"
          value={chartRange}
          onChange={(event) => onChartRangeChange(event.target.value)}
        >
          {rangesToShow.map((range) => (
            <option key={range} value={range}>
              {range}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
