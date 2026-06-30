/**
 * API base URL for backend calls.
 *
 * Empty string in dev uses Vite's /api proxy (see vite.config.js).
 * Override with VITE_API_BASE_URL when pointing at a remote API.
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
