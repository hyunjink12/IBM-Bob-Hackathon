import { useEffect, useMemo, useState } from 'react'

import { ApiError, BackendApiClient } from '../managers/backend_api_client.js'

/**
 * @typedef {'loading' | 'success' | 'error'} HelloWorldStatus
 */

/**
 * React hook that loads the backend hello message on mount.
 *
 * Casual: fetches hello world or captures what went wrong.
 *
 * Separates async loading logic from the view so App stays a dumb renderer
 * and we can reuse the same state machine in tests or other screens later.
 *
 * @param {BackendApiClient} [apiClient]
 * @returns {{ status: HelloWorldStatus, displayText: string | null, errorDetail: string | null }}
 */
export function useHelloWorldViewModel(apiClient) {
  const client = useMemo(
    () => apiClient ?? new BackendApiClient(),
    [apiClient],
  )

  const [status, setStatus] = useState('loading')
  const [displayText, setDisplayText] = useState(null)
  const [errorDetail, setErrorDetail] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function loadHello() {
      try {
        const payload = await client.fetchHello()
        if (cancelled) return

        setDisplayText(`${payload.message} (200 OK)`)
        setErrorDetail(null)
        setStatus('success')
      } catch (error) {
        if (cancelled) return

        setDisplayText(null)
        setErrorDetail(formatHelloError(error))
        setStatus('error')
      }
    }

    loadHello()

    return () => {
      cancelled = true
    }
  }, [client])

  return { status, displayText, errorDetail }
}

/**
 * Turn fetch failures into a single human-readable string for the UI.
 *
 * @param {unknown} error
 * @returns {string}
 */
function formatHelloError(error) {
  if (error instanceof ApiError) {
    if (error.statusCode === 0) {
      return `Cannot reach backend: ${error.responseBody}`
    }

    return `HTTP ${error.statusCode}: ${error.responseBody}`
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'An unexpected error occurred'
}
