import { API_BASE_URL } from '../config/api_config.js'

/**
 * HTTP client for dashboard API endpoints.
 */
export class DashboardApiClient {
  constructor(baseUrl = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  async fetchOverview() {
    return this._get('/api/dashboard/overview')
  }

  async fetchMargins({ range, windowType, lookbackDays }) {
    const params = new URLSearchParams({
      range,
      windowType,
      lookbackDays: String(lookbackDays),
    })
    return this._get(`/api/dashboard/margins?${params}`)
  }

  async fetchSpread({ range }) {
    return this._get(`/api/dashboard/spread?range=${encodeURIComponent(range)}`)
  }

  async fetchWarnings() {
    return this._get('/api/dashboard/warnings')
  }

  async fetchPanel5() {
    return this._get('/api/dashboard/panel5')
  }

  async _get(path) {
    const response = await fetch(`${this.baseUrl}${path}`)
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `Request failed: ${response.status}`)
    }
    return response.json()
  }
}
