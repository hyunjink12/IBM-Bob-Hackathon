import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardConfig } from '../config/dashboard_config.js'
import { DashboardApiClient } from '../managers/dashboard_api_client.js'

/** Approximate span (days) each range token covers. YTD is date-dependent. */
function rangeToApproxDays(rangeToken) {
  const map = {
    '1W': 7, '1M': 30, '3M': 90, '6M': 180,
    '1Y': 365, '2Y': 730, '5Y': 1825, ALL: 3650,
  }
  const token = String(rangeToken).toUpperCase()
  if (token === 'YTD') {
    const start = new Date(new Date().getFullYear(), 0, 1)
    return Math.round((Date.now() - start.getTime()) / 86_400_000)
  }
  return map[token] ?? 365
}

/** Does the current range have enough span to sensibly plot at this granularity? */
function isGranularityAllowedForRange(granularity, range) {
  const minDays = dashboardConfig.granularityMinDays?.[granularity] ?? 0
  return rangeToApproxDays(range) >= minDays
}

/** Widest granularity that still fits inside `range`, or 'daily' as fallback. */
function widestAllowedGranularity(range) {
  return (
    ['monthly', 'weekly', 'daily'].find((g) =>
      isGranularityAllowedForRange(g, range),
    ) ?? 'daily'
  )
}

/**
 * View-model hook for the ethanol crush dashboard.
 *
 * Casual: loads all dashboard panels once (or when range changes).
 *
 * Keeps fetch orchestration out of the view. The API client must be stable
 * across renders — a fresh default instance every render would recreate
 * `refresh` and retrigger the effect in a tight request loop.
 */
export function useDashboardViewModel(apiClient) {
  const client = useMemo(
    () => apiClient ?? new DashboardApiClient(),
    [apiClient],
  )

  const [chartRange, setChartRange] = useState(dashboardConfig.defaultChartRange)
  const [chartGranularity, setChartGranularity] = useState(
    dashboardConfig.defaultGranularity,
  )
  const [overview, setOverview] = useState(null)
  const [margins, setMargins] = useState(null)
  const [spread, setSpread] = useState(null)
  const [warnings, setWarnings] = useState(null)
  const [backtest, setBacktest] = useState(null)
  const [briefing, setBriefing] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const queryParams = useMemo(
    () => ({
      range: chartRange,
      windowType: dashboardConfig.zScore.defaultWindowType,
      lookbackDays: dashboardConfig.zScore.defaultLookbackDays,
      granularity: chartGranularity,
    }),
    [chartRange, chartGranularity],
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, marginsData, spreadData, warningsData, backtestData, briefingData] =
        await Promise.all([
          client.fetchOverview(),
          client.fetchMargins(queryParams),
          client.fetchSpread({ range: chartRange, granularity: chartGranularity }),
          client.fetchWarnings(),
          client.fetchBacktest(),
          client.fetchBriefing(),
        ])
      setOverview(overviewData)
      setMargins(marginsData)
      setSpread(spreadData)
      setWarnings(warningsData)
      setBacktest(backtestData)
      setBriefing(briefingData)
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [client, chartRange, chartGranularity, queryParams])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    chartRange,
    setChartRange,
    chartGranularity,
    setChartGranularity,
    overview,
    margins,
    spread,
    warnings,
    backtest,
    briefing,
    loading,
    error,
    refresh,
    config: dashboardConfig,
  }
}
