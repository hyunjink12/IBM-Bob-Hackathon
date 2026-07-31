/**
 * Central dashboard tunables (not secrets).
 * Z-score window, signal thresholds, chart defaults, and tooltip copy live here.
 */
export const dashboardConfig = {
  defaultChartRange: '1Y',
  chartRanges: ['1W', '1M', '3M', '6M', 'YTD', '1Y', '2Y', '5Y', 'ALL'],
  defaultGranularity: 'daily',
  granularities: [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
  ],
  // Minimum range span (days) each granularity needs to plot enough bars.
  // Weekly wants ~4 bars → 1M+. Monthly wants ~4 bars → 6M+.
  granularityMinDays: {
    daily: 0,
    weekly: 30,
    monthly: 180,
  },
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
    margin_per_gallon:
      'Same crush margin expressed per gallon of ethanol output.',
    z_score: 'How today’s margin compares to the selected historical window.',
    signal_label: 'Rich / weak labels come from the z-score bands in config.',
    spread:
      'CME-standard ethanol crush spread: 2.8 × ethanol $/gal − corn $/bu (Iowa CARD dry-mill yield). Flags feedstock-vs-output dislocation without DDGS/gas/opex noise.',
  },
}
