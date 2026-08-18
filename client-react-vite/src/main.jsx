import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Apply the saved theme BEFORE React first renders so viewers don't see a
// flash of the wrong theme on load. Falls back to dark (the historical
// default) when nothing is saved and the OS doesn't hint a preference.
;(function applyStoredTheme() {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') {
      document.documentElement.dataset.theme = saved
      return
    }
    const prefersLight =
      window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
    document.documentElement.dataset.theme = prefersLight ? 'light' : 'dark'
  } catch {
    document.documentElement.dataset.theme = 'dark'
  }
})()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
