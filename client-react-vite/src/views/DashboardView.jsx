import { useDashboardViewModel } from '../viewmodels/dashboard_view_model.js'
import { SeedDataWarningBanner } from '../components/SeedDataWarningBanner.jsx'
import { MethodologyFooter } from './MethodologyFooter.jsx'
import { CornEthanolSpreadPanel } from './panels/CornEthanolSpreadPanel.jsx'
import { CrushMarginPanel } from './panels/CrushMarginPanel.jsx'
import { MarketOverviewPanel } from './panels/MarketOverviewPanel.jsx'
import { WarningSignalsPanel } from './panels/WarningSignalsPanel.jsx'

/**
 * Main single-page ethanol crush dashboard.
 *
 * Casual: wires panels + the seed-data warning when demo rows are in play.
 */
export function DashboardView() {
  const {
    chartRange,
    setChartRange,
    chartGranularity,
    setChartGranularity,
    overview,
    margins,
    spread,
    warnings,
    backtest,
    loading,
    error,
    refresh,
    config,
  } = useDashboardViewModel()

  return (
    <div className="dashboard">
      <SeedDataWarningBanner dataProvenance={overview?.data_provenance} />

      <header className="dashboard__header">
        <div>
          <p className="dashboard__eyebrow">Corn Ethanol Arb Monitor</p>
          <h1>Ethanol Crush Margin Dashboard</h1>
        </div>
        <div className="dashboard__controls">
          <button type="button" onClick={refresh}>
            Refresh
          </button>
        </div>
      </header>

      {loading && <p className="dashboard__status">Loading dashboard…</p>}
      {error && <p className="dashboard__error">{error}</p>}

      <main className="dashboard__grid">
        <MarketOverviewPanel overview={overview} />
        <CrushMarginPanel
          margins={margins}
          config={config}
          chartRange={chartRange}
          onChartRangeChange={setChartRange}
          chartGranularity={chartGranularity}
          onChartGranularityChange={setChartGranularity}
        />
        <CornEthanolSpreadPanel spread={spread} config={config} />
        <WarningSignalsPanel warnings={warnings} backtest={backtest} />
      </main>

      <MethodologyFooter />
    </div>
  )
}
