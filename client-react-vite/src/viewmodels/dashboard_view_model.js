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
  const [chartGranularity, setChartGranularity] = useState(
    dashboardConfig.defaultGranularity,
  )

  // Independent controls: neither dropdown constrains the other. The user
  // can pick any (range, granularity) combination; if a short range paired
  // with a long granularity yields one bar, that's the user's intent.
  const [cotChartRange, setCotChartRange] = useState(
    dashboardConfig.defaultChartRange,
  )
  const [overview, setOverview] = useState(null)
  const [margins, setMargins] = useState(null)
  const [spread, setSpread] = useState(null)
  const [warnings, setWarnings] = useState(null)
  const [backtest, setBacktest] = useState(null)
  const [briefing, setBriefing] = useState(null)
  const [eiaReleases, setEiaReleases] = useState(null)
  const [tape, setTape] = useState(null)
  const [cotPositioning, setCotPositioning] = useState(null)
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
      const [
        overviewData,
        marginsData,
        spreadData,
        warningsData,
        backtestData,
        briefingData,
        eiaReleasesData,
        tapeData,
        cotPositioningData,
      ] = await Promise.all([
        client.fetchOverview(),
        client.fetchMargins(queryParams),
        client.fetchSpread({ range: chartRange, granularity: chartGranularity }),
        client.fetchWarnings(),
        client.fetchBacktest(),
        client.fetchBriefing(),
        client.fetchEiaReleases({ range: chartRange }),
        client.fetchTape(),
        client.fetchCotPositioning({ range: cotChartRange }),
      ])
      setOverview(overviewData)
      setMargins(marginsData)
      setSpread(spreadData)
      setWarnings(warningsData)
      setBacktest(backtestData)
      setBriefing(briefingData)
      setEiaReleases(eiaReleasesData)
      setTape(tapeData)
      setCotPositioning(cotPositioningData)
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [client, chartRange, chartGranularity, cotChartRange, queryParams])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    chartRange,
    setChartRange,
    chartGranularity,
    setChartGranularity,
    cotChartRange,
    setCotChartRange,
    overview,
    margins,
    spread,
    warnings,
    backtest,
    briefing,
    eiaReleases,
    tape,
    cotPositioning,
    loading,
    error,
    refresh,
    config: dashboardConfig,
  }
}
