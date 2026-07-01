/**
 * Central dashboard tunables (not secrets).
 * Z-score window, signal thresholds, chart defaults, and tooltip copy live here.
 */
export const dashboardConfig = {
  defaultChartRange: '1Y',
  chartRanges: ['1Y', '2Y', '5Y', 'ALL'],
  zScore: {
    defaultLookbackDays: 1825,
    defaultWindowType: 'rolling',
    supportedWindowTypes: ['rolling', 'expanding'],
  },
  signalThresholds: {
    rich: 1.5,
    elevated: 1.0,
    soft: -1.0,
    weak: -1.5,
  },
  signalColors: {
    rich: '#3dd68c',
    elevated: '#8fe8b8',
    normal: '#9aa5b1',
    soft: '#f0a878',
    weak: '#f07178',
  },
  tooltips: {
    margin_per_bushel:
      'Estimated crush margin per bushel of corn after ethanol, DDGS, gas, and opex.',
    z_score: 'How today’s margin compares to the selected historical window.',
    signal_label: 'Rich / weak labels come from the z-score bands in config.',
    spread:
      'Net ethanol coproduct value per bushel minus corn — flags corn vs output dislocation.',
  },
}
