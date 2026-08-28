from collections.abc import Callable

import httpx

_DRIVE_API_HOST = "www.googleapis.com"
_GENERATE_IDS_URL = "https://www.googleapis.com/drive/v3/files/generateIds"


class DriveApiError(ValueError):
    """Raised when a Drive response cannot prove the requested safe operation."""


class DriveApiClient:
    """Makes only fixed, fail-closed Drive API requests."""

    def __init__(self, http_client: httpx.Client) -> None:
        self._http_client = http_client

    def generate_ids(
        self, access_token: str, count: int, *, before_request: Callable[[], None]
    ) -> tuple[str, ...]:
        if not 1 <= count <= 3 or not 1 <= len(access_token) <= 4096:
            raise DriveApiError("The Drive request is invalid.")
        before_request()
        try:
            response = self._http_client.get(
                _GENERATE_IDS_URL,
                params={"count": str(count), "space": "drive", "type": "files"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as error:
            raise DriveApiError("Google Drive is temporarily unavailable.") from error
        if response.status_code != 200:
            raise DriveApiError("Google Drive did not reserve backup identifiers.")
        try:
            payload = response.json()
        except ValueError as error:
            raise DriveApiError("The Google Drive response is invalid.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("ids"), list):
            raise DriveApiError("The Google Drive response is invalid.")
        ids = tuple(payload["ids"])
        if len(ids) != count or any(not isinstance(value, str) or not value for value in ids):
            raise DriveApiError("The Google Drive response is invalid.")
        return ids
