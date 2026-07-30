"""IBM watsonx.ai client — IAM token exchange + Granite text generation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

_logger = logging.getLogger(__name__)

_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
_GENERATION_PATH = "/ml/v1/text/generation"
_GENERATION_API_VERSION = "2024-05-01"


@dataclass
class _CachedToken:
    """Short-lived IAM bearer token with expiry tracking."""

    access_token: str
    expires_at: float  # Unix timestamp


class WatsonxClient:
    """
    Thin HTTP wrapper over the watsonx.ai text generation endpoint.

    Casual: asks Granite to write one trader briefing sentence at a time.

    IBM Cloud IAM tokens last ~1 hour. We exchange the API key for a token
    once, cache it, and re-exchange when it is within 5 minutes of expiry
    so individual requests never block on auth renewal.

    The client is stateless with respect to the dashboard data — callers
    pass structured context and receive a prose string. No prompt engineering
    leaks into the manager layer.
    """

    def __init__(
        self,
        api_key: str,
        project_id: str,
        base_url: str = "https://us-south.ml.cloud.ibm.com",
        model_id: str = "ibm/granite-3-8b-instruct",
    ) -> None:
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._token_cache: _CachedToken | None = None

    @property
    def is_configured(self) -> bool:
        """True when both the API key and project ID are present."""
        return bool(self._api_key and self._project_id)

    def generate(self, prompt: str, *, max_new_tokens: int = 350, temperature: float = 0.2) -> str:
        """
        Call the Granite text generation endpoint and return the generated text.

        Raises ``RuntimeError`` if the client is not configured or the API call fails.
        """
        if not self.is_configured:
            raise RuntimeError("WatsonxClient is not configured: set api_key and project_id")

        bearer = self._get_bearer_token()
        url = f"{self._base_url}{_GENERATION_PATH}?version={_GENERATION_API_VERSION}"
        payload = {
            "model_id": self._model_id,
            "project_id": self._project_id,
            "input": prompt,
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "repetition_penalty": 1.05,
            },
        }
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"watsonx.ai API error {exc.response.status_code}: {exc.response.text}") from exc

        data = response.json()
        results = data.get("results", [])
        if not results:
            raise RuntimeError(f"watsonx.ai returned no results: {data}")
        return results[0].get("generated_text", "").strip()

    # ------------------------------------------------------------------
    # IAM token exchange
    # ------------------------------------------------------------------

    def _get_bearer_token(self) -> str:
        now = time.time()
        if self._token_cache and self._token_cache.expires_at - now > 300:
            return self._token_cache.access_token

        _logger.debug("Refreshing IBM Cloud IAM token")
        try:
            resp = httpx.post(
                _IAM_TOKEN_URL,
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": self._api_key,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"IBM IAM token exchange failed {exc.response.status_code}: {exc.response.text}") from exc

        token_data = resp.json()
        access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_cache = _CachedToken(
            access_token=access_token,
            expires_at=now + expires_in,
        )
        return access_token
