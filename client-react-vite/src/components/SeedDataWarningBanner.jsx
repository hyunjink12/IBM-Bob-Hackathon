/**
 * Full-bleed banner when the API says seed/demo data is driving the dashboard.
 *
 * Casual: giant “this is fake” warning so nobody mistakes seed for live prices.
 *
 * Renders nothing when provenance is missing or live feeds won the merge.
 * When `using_seed_data` is true, shows a sticky, high-contrast strip listing
 * which series are still synthetic so operators can tell at a glance.
 */
export function SeedDataWarningBanner({ dataProvenance }) {
  if (!dataProvenance?.using_seed_data) {
    return null
  }

  const seededLabels = (dataProvenance.seeded_series ?? [])
    .map((seriesId) => seriesId.replaceAll('_', ' '))
    .join(' · ')

  return (
    <aside
      className="seed-data-warning"
      role="alert"
      aria-live="assertive"
    >
      <div className="seed-data-warning__stripe" aria-hidden="true" />
      <div className="seed-data-warning__body">
        <p className="seed-data-warning__eyebrow">Demo data active</p>
        <p className="seed-data-warning__title">
          SYNTHETIC SEED DATA — NOT LIVE MARKET PRICES
        </p>
        <p className="seed-data-warning__message">
          {dataProvenance.message ??
            'One or more series are powered by generated seed history for local demo.'}
        </p>
        {seededLabels ? (
          <p className="seed-data-warning__series">
            Seeded series: {seededLabels}
          </p>
        ) : null}
      </div>
    </aside>
  )
}
