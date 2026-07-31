/**
 * Physical / Financial tab switcher for the dashboard body.
 *
 * Client-side state only — no route change, no reload. Fetch state stays
 * warm across switches so toggling is instant.
 */
export function DashboardTabs({ active, onChange }) {
  const tabs = [
    { id: 'physical', label: 'Physical', hint: 'Crush margin · Inventory' },
    { id: 'financial', label: 'Financial', hint: 'Spread · COT positioning' },
  ]
  return (
    <div className="dashboard-tabs" role="tablist" aria-label="Dashboard section">
      {tabs.map((tab) => {
        const isActive = tab.id === active
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={isActive}
            className={`dashboard-tabs__tab${isActive ? ' dashboard-tabs__tab--active' : ''}`}
            onClick={() => onChange(tab.id)}
          >
            <span className="dashboard-tabs__label">{tab.label}</span>
            <span className="dashboard-tabs__hint">{tab.hint}</span>
          </button>
        )
      })}
    </div>
  )
}
