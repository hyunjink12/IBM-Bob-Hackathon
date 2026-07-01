/**
 * Panel 4 — rule-based warning signal cards.
 */
export function WarningSignalsPanel({ warnings }) {
  if (!warnings) {
    return <section className="panel">Loading warning signals…</section>
  }

  return (
    <section className="panel">
      <header className="panel__header">
        <h2>Inventory / Production Stress</h2>
        <span className="panel__meta">As of {warnings.as_of ?? '—'}</span>
      </header>
      {warnings.warnings.length === 0 ? (
        <p className="empty-state">No active warning signals for the latest session.</p>
      ) : (
        <div className="warning-grid">
          {warnings.warnings.map((warning) => (
            <article
              key={warning.signal_type}
              className={`warning-card warning-card--${warning.severity}`}
            >
              <h3>{warning.signal_type.replaceAll('_', ' ')}</h3>
              <p>{warning.message}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
