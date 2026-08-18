import { useEffect, useState } from 'react'

/**
 * Small settings-icon button that toggles between dark and light themes.
 *
 * Theme choice is persisted in localStorage under `theme`. The initial value
 * is applied to <html> in main.jsx BEFORE React first renders — this component
 * only handles user-initiated toggles after that, so viewers never see a
 * flash of the wrong theme on page load.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState(() =>
    document.documentElement.dataset.theme === 'light' ? 'light' : 'dark',
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('theme', theme)
    } catch {
      // localStorage can throw in private browsing on some browsers — the
      // in-memory state still tracks the toggle for this session.
    }
  }, [theme])

  const isDark = theme === 'dark'
  const nextLabel = isDark ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={nextLabel}
      title={nextLabel}
    >
      {isDark ? <SunIcon /> : <MoonIcon /> }
    </button>
  )
}

/* Simple 16×16 sun / moon glyphs — inline SVG so they inherit currentColor
   and match the surrounding text color in either theme. */
function SunIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}
