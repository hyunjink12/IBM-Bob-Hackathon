/**
 * Methodology footer explaining CARD formula and limitations.
 */
export function MethodologyFooter() {
  return (
    <footer className="methodology-footer">
      <h2>How this dashboard works</h2>
      <p>
        We use a simplified Iowa State CARD dry-mill model: 1 bushel of corn plus
        72.8k BTU natural gas produces 2.8 gallons ethanol, 17 lbs DDGS, and 0.7
        lbs corn oil. DDGS is quoted in <strong>$/short ton</strong> throughout the UI.
      </p>
      <p>
        Ethanol <strong>price</strong> comes from CBOT EH front-month futures; ethanol
        <strong> production and stocks</strong> come from EIA weekly data. This is a
        decision-support tool, not an institutional margin model — mixed bases and
        seeded fallbacks may apply when live feeds are unavailable.
      </p>
      <p>
        Z-score bands: Rich &gt; +1.5, Elevated +1 to +1.5, Normal −1 to +1, Soft −1.5
        to −1, Weak &lt; −1.5. Negative margins are shown as-is.
      </p>
    </footer>
  )
}
