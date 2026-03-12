import requests

from solo.hub.auth import ensure_authenticated, get_user_profile
from solo.hub.constants import (
    MODEL_FILES_ENDPOINT,
    MODEL_INFO_ENDPOINT,
    MODEL_LIST_ENDPOINT,
    SOLO_HUB_API_BASE,
    USER_PROFILE_ENDPOINT,
)
from solo.hub.errors import SoloAuthError, SoloHubError, SoloModelNotFoundError


class SoloHubClient:
    """HTTP client for the Solo Hub API."""

    def __init__(self, token: str | None = None, api_base: str | None = None):
        self.api_base = api_base or SOLO_HUB_API_BASE
        self._token = token

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = ensure_authenticated()
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.api_base}{path}"
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        except requests.ConnectionError:
            raise SoloHubError(
                "Could not connect to Solo Hub. Check your internet connection and try again."
            )
        except requests.Timeout:
            raise SoloHubError(
                "Request to Solo Hub timed out. Please try again later."
            )
        if resp.status_code == 401:
            raise SoloAuthError("Token is invalid or expired. Run 'solo login' to re-authenticate.")
        return resp

    def get_model_info(self, identifier: str) -> dict:
        """
        Get model details by name or ID.
        The identifier should be the model name (not org/model).
        Returns the full model object including id, name, organizationId, etc.
        """
        path = MODEL_INFO_ENDPOINT.format(identifier=identifier)
        resp = self._get(path)
        if resp.status_code == 404:
            raise SoloModelNotFoundError(
                f"Model '{identifier}' not found on Solo Hub. "
                "Check the model name and ensure you have access."
            )
        if resp.status_code != 200:
            # The API may return 500 when model is not found — detect and raise as not-found
            if resp.status_code == 500:
                try:
                    body = resp.json()
                    error_msg = body.get("error", "")
                except Exception:
                    error_msg = ""
                if "getting models" in error_msg.lower():
                    raise SoloModelNotFoundError(
                        f"Model '{identifier}' not found on Solo Hub. "
                        "Check the model name and ensure you have access."
                    )
            raise SoloHubError(
                f"Solo Hub returned an unexpected error ({resp.status_code}). "
                "Please try again later or contact support if the issue persists."
            )
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type:
            raise SoloModelNotFoundError(
                f"Model '{identifier}' not found on Solo Hub. "
                "Check the model name and ensure you have access."
            )
        return resp.json()

    def list_models(
        self,
        page: int = 1,
        limit: int = 25,
        model_type: str | None = None,
        search: str | None = None,
    ) -> dict:
        """List models with pagination and optional filtering."""
        params = {"page": page, "limit": limit}
        if model_type:
            params["type"] = model_type
        if search:
            params["search"] = search

        resp = self._get(MODEL_LIST_ENDPOINT, params=params)
        if resp.status_code != 200:
            raise SoloHubError(f"Failed to list models: {resp.status_code} {resp.text}")
        return resp.json()

    def get_model_files(self, org_id: str, model_id: str) -> dict:
        """
        Get all files for a model with presigned download URLs.
        Returns a dict with folder names as keys and lists of file objects as values.
        Each file object has: name, url (presigned GCS URL), fileSize.
        """
        path = MODEL_FILES_ENDPOINT.format(org_id=org_id, model_id=model_id)
        resp = self._get(path)
        if resp.status_code == 404:
            raise SoloModelNotFoundError(
                f"Model files not found for org={org_id}, model={model_id}."
            )
        if resp.status_code != 200:
            raise SoloHubError(
                f"Solo Hub returned an unexpected error ({resp.status_code}) while fetching model files. "
                "Please try again later or contact support if the issue persists."
            )
        return resp.json()

    def whoami(self) -> dict:
        """Get the current user's profile with organization and subscription info."""
        return get_user_profile(self.token)
