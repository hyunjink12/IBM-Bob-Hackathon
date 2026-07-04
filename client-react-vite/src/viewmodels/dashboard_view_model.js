import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardConfig } from '../config/dashboard_config.js'
import { DashboardApiClient } from '../managers/dashboard_api_client.js'

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
  const [overview, setOverview] = useState(null)
  const [margins, setMargins] = useState(null)
  const [spread, setSpread] = useState(null)
  const [warnings, setWarnings] = useState(null)
  const [panel5, setPanel5] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const queryParams = useMemo(
    () => ({
      range: chartRange,
      windowType: dashboardConfig.zScore.defaultWindowType,
      lookbackDays: dashboardConfig.zScore.defaultLookbackDays,
    }),
    [chartRange],
  )

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [overviewData, marginsData, spreadData, warningsData, panel5Data] =
        await Promise.all([
          client.fetchOverview(),
          client.fetchMargins(queryParams),
          client.fetchSpread({ range: chartRange }),
          client.fetchWarnings(),
          client.fetchPanel5(),
        ])
      setOverview(overviewData)
      setMargins(marginsData)
      setSpread(spreadData)
      setWarnings(warningsData)
      setPanel5(panel5Data)
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [client, chartRange, queryParams])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    chartRange,
    setChartRange,
    overview,
    margins,
    spread,
    warnings,
    panel5,
    loading,
    error,
    refresh,
    config: dashboardConfig,
  }
}
