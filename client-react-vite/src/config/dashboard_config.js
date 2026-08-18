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
      'Plant operating margin per bushel of corn: ethanol + coproduct revenue minus corn + gas + opex costs. Excludes the D6 RIN regulatory-value equivalent, which is shown separately in the Ethanol Economics Decomposition panel.',
    margin_per_gallon:
      'Plant operating margin per gallon of ethanol produced (per-bushel margin ÷ 2.8 gal/bu). Physical crush P&L only; RIN regulatory value is separate.',
    z_score: 'How today’s plant operating margin compares to the selected historical window.',
    signal_label: 'Rich / weak labels come from the z-score bands in config.',
    spread:
      'Simple ethanol/corn spread: 2.8 × ethanol $/gal − corn $/bu using the Iowa CARD dry-mill ethanol yield. This is a two-leg market screen for the feedstock-vs-output relationship, not the CME/CBOT-listed corn-for-ethanol crush and not a complete plant margin. DDGS, corn oil, natural gas, opex, and D6 RIN value are excluded.',
  },
}
