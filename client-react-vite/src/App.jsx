import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/react'
import { DashboardView } from './views/DashboardView.jsx'
import './styles/dashboard-dark.css'

function App() {
  return (
    <>
      <DashboardView />
      {/* Vercel Analytics — auto-disabled in dev, fires page + custom events
          from the deployed origin. No config needed; picks up the project
          from the Vercel-injected env at build time. */}
      <Analytics />
      <SpeedInsights />
    </>
  )
}

export default App
