import { API_BASE_URL } from '../config/api_config.js'

/**
 * Thrown when the backend responds with a non-2xx status.
 */
export class ApiError extends Error {
  constructor(statusCode, responseBody) {
    super(`Request failed with status ${statusCode}`)
    this.name = 'ApiError'
    this.statusCode = statusCode
    this.responseBody = responseBody
  }
}

/**
 * Thin HTTP client for the corn-ethanol backend.
 *
 * Casual: talks to FastAPI for us.
 *
 * Centralizes fetch details (base URL, error mapping) so views only care
 * about success payloads or structured failures.
 */
export class BackendApiClient {
  constructor(baseUrl = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  /**
   * GET /api/hello — used on page load to verify backend connectivity.
   *
   * @returns {Promise<{ message: string }>}
   */
  async fetchHello() {
    let response

    try {
      response = await fetch(`${this.baseUrl}/api/hello`)
    } catch (networkError) {
      throw new ApiError(
        0,
        networkError instanceof Error
          ? networkError.message
          : 'Network request failed',
      )
    }

    const responseBody = await response.text()

    if (!response.ok) {
      throw new ApiError(response.status, responseBody || response.statusText)
    }

    try {
      return JSON.parse(responseBody)
    } catch {
      throw new ApiError(response.status, 'Response was not valid JSON')
    }
  }
}
