import { useDashboardViewModel } from '../viewmodels/dashboard_view_model.js'
import { SeedDataWarningBanner } from '../components/SeedDataWarningBanner.jsx'
import { MethodologyFooter } from './MethodologyFooter.jsx'
import { CornEthanolSpreadPanel } from './panels/CornEthanolSpreadPanel.jsx'
import { CrushMarginPanel } from './panels/CrushMarginPanel.jsx'
import { MarketOverviewPanel } from './panels/MarketOverviewPanel.jsx'
import { Panel5Placeholder } from './panels/Panel5Placeholder.jsx'
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
    overview,
    margins,
    spread,
    warnings,
    panel5,
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
          <label htmlFor="chart-range">Range</label>
          <select
            id="chart-range"
            value={chartRange}
            onChange={(event) => setChartRange(event.target.value)}
          >
            {config.chartRanges.map((range) => (
              <option key={range} value={range}>
                {range}
              </option>
            ))}
          </select>
          <button type="button" onClick={refresh}>
            Refresh
          </button>
        </div>
      </header>

      {loading && <p className="dashboard__status">Loading dashboard…</p>}
      {error && <p className="dashboard__error">{error}</p>}

      <main className="dashboard__grid">
        <MarketOverviewPanel overview={overview} />
        <CrushMarginPanel margins={margins} config={config} />
        <CornEthanolSpreadPanel spread={spread} config={config} />
        <WarningSignalsPanel warnings={warnings} />
        <Panel5Placeholder panel5={panel5} />
      </main>

      <MethodologyFooter />
    </div>
  )
}
