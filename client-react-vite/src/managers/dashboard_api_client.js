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

  async fetchMargins({ range, windowType, lookbackDays, granularity }) {
    const params = new URLSearchParams({
      range,
      windowType,
      lookbackDays: String(lookbackDays),
      granularity,
    })
    return this._get(`/api/dashboard/margins?${params}`)
  }

  async fetchSpread({ range, granularity }) {
    const params = new URLSearchParams({ range, granularity })
    return this._get(`/api/dashboard/spread?${params}`)
  }

  async fetchBriefing() {
    return this._get('/api/dashboard/briefing')
  }

  async askPresetQuestion(questionId) {
    const response = await fetch(`${this.baseUrl}/api/dashboard/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: questionId }),
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `Request failed: ${response.status}`)
    }
    return response.json()
  }

  async fetchWarnings() {
    return this._get('/api/dashboard/warnings')
  }

  async fetchBacktest() {
    return this._get('/api/dashboard/backtest')
  }

  async fetchEiaReleases({ range }) {
    const params = new URLSearchParams({ range })
    return this._get(`/api/dashboard/eia-releases?${params}`)
  }

  async fetchTape() {
    return this._get('/api/dashboard/tape')
  }

  async fetchCotPositioning({ range }) {
    const params = new URLSearchParams({ range })
    return this._get(`/api/dashboard/cot-positioning?${params}`)
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
