import { useMemo, useState } from 'react'
import { useDashboardViewModel } from '../viewmodels/dashboard_view_model.js'
import { DashboardApiClient } from '../managers/dashboard_api_client.js'
import { SeedDataWarningBanner } from '../components/SeedDataWarningBanner.jsx'
import { ThemeToggle } from '../components/ThemeToggle.jsx'
import { BriefingStrip } from './BriefingStrip.jsx'
import { ChartControls } from './ChartControls.jsx'
import { DashboardTabs } from './DashboardTabs.jsx'
import { MethodologyFooter } from './MethodologyFooter.jsx'
import { TickerTape } from './TickerTape.jsx'
import { CornEthanolSpreadPanel } from './panels/CornEthanolSpreadPanel.jsx'
import { CotPositioningPanel } from './panels/CotPositioningPanel.jsx'
import { CrushMarginPanel } from './panels/CrushMarginPanel.jsx'
import { MarginCompositionPanel } from './panels/MarginCompositionPanel.jsx'
import { MarketOverviewPanel } from './panels/MarketOverviewPanel.jsx'
import { WarningSignalsPanel } from './panels/WarningSignalsPanel.jsx'

/**
 * Main single-page ethanol crush dashboard.
 *
 * Layout: always-visible header (tape / seed banner / briefing / market
 * overview) plus a Physical/Financial tab switcher for the body panels.
 *
 * The top ChartControls toolbar binds to the ACTIVE tab's own range/
 * granularity state, so changing knobs on Financial never mutates Physical
 * and vice versa. The COT chart owns its own range on top of that.
 */
export function DashboardView() {
  const {
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
    config,
  } = useDashboardViewModel()

  const [activeTab, setActiveTab] = useState('physical')
  // Stable client instance for the preset-question chips inside BriefingStrip.
  const apiClient = useMemo(() => new DashboardApiClient(), [])

  const activeControls =
    activeTab === 'physical'
      ? {
          chartRange: physicalChartRange,
          onChartRangeChange: setPhysicalChartRange,
          chartGranularity: physicalChartGranularity,
          onChartGranularityChange: setPhysicalChartGranularity,
        }
      : {
          chartRange: financialChartRange,
          onChartRangeChange: setFinancialChartRange,
          chartGranularity: financialChartGranularity,
          onChartGranularityChange: setFinancialChartGranularity,
        }

  return (
    <div className="dashboard">
      <TickerTape tape={tape} />
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
          <ThemeToggle />
        </div>
      </header>

      <BriefingStrip briefing={briefing} apiClient={apiClient} />

      {loading && <p className="dashboard__status">Loading dashboard…</p>}
      {error && <p className="dashboard__error">{error}</p>}

      <main className="dashboard__grid">
        <MarketOverviewPanel overview={overview} />
      </main>

      <div className="dashboard-tabs-row">
        <DashboardTabs active={activeTab} onChange={setActiveTab} />
        <ChartControls config={config} scopeId={activeTab} {...activeControls} />
      </div>

      <main className="dashboard__grid">
        {activeTab === 'physical' ? (
          <>
            <CrushMarginPanel
              margins={margins}
              config={config}
              eiaReleases={eiaReleases?.releases}
            />
            <WarningSignalsPanel warnings={warnings} backtest={backtest} />
            <MarginCompositionPanel composition={margins?.composition} />
          </>
        ) : (
          <>
            <CornEthanolSpreadPanel spread={spread} config={config} />
            <CotPositioningPanel
              cotPositioning={cotPositioning}
              config={config}
              chartRange={cotChartRange}
              onChartRangeChange={setCotChartRange}
            />
          </>
        )}
      </main>

      <MethodologyFooter />
    </div>
  )
}
