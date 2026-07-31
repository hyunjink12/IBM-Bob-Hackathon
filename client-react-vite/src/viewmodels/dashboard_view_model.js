import { useCallback, useEffect, useMemo, useState } from 'react'
import { dashboardConfig } from '../config/dashboard_config.js'
import { DashboardApiClient } from '../managers/dashboard_api_client.js'

/**
 * View-model hook for the ethanol crush dashboard.
 *
 * Chart-control state is split by scope so tabs don't share knobs:
 *   - physicalChartRange/Granularity → drives margin chart + EIA release markers
 *   - financialChartRange/Granularity → drives spread chart
 *   - cotChartRange                   → drives COT positioning chart only
 *
 * Range and granularity within a scope also operate independently — neither
 * dropdown constrains the other. If the user picks Monthly + 1W, they get
 * one bar; that's the user's intent.
 */
export function useDashboardViewModel(apiClient) {
  const client = useMemo(
    () => apiClient ?? new DashboardApiClient(),
    [apiClient],
  )

  const [physicalChartRange, setPhysicalChartRange] = useState(
    dashboardConfig.defaultChartRange,
  )
  const [physicalChartGranularity, setPhysicalChartGranularity] = useState(
    dashboardConfig.defaultGranularity,
  )
  const [financialChartRange, setFinancialChartRange] = useState(
    dashboardConfig.defaultChartRange,
  )
  const [financialChartGranularity, setFinancialChartGranularity] = useState(
    dashboardConfig.defaultGranularity,
  )
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

  const marginsQuery = useMemo(
    () => ({
      range: physicalChartRange,
      windowType: dashboardConfig.zScore.defaultWindowType,
      lookbackDays: dashboardConfig.zScore.defaultLookbackDays,
      granularity: physicalChartGranularity,
    }),
    [physicalChartRange, physicalChartGranularity],
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
        client.fetchMargins(marginsQuery),
        client.fetchSpread({
          range: financialChartRange,
          granularity: financialChartGranularity,
        }),
        client.fetchWarnings(),
        client.fetchBacktest(),
        client.fetchBriefing(),
        client.fetchEiaReleases({ range: physicalChartRange }),
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
  }, [
    client,
    marginsQuery,
    physicalChartRange,
    financialChartRange,
    financialChartGranularity,
    cotChartRange,
  ])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    physicalChartRange,
    setPhysicalChartRange,
    physicalChartGranularity,
    setPhysicalChartGranularity,
    financialChartRange,
    setFinancialChartRange,
    financialChartGranularity,
    setFinancialChartGranularity,
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
