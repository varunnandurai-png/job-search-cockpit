from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx

from job_search_cockpit.phase2.finalisation import (
    FinalResumeArtifact,
    LocalResumeFinalisationService,
)

_DRIVE_API_HOST = "www.googleapis.com"
_GENERATE_IDS_URL = "https://www.googleapis.com/drive/v3/files/generateIds"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_FOLDER_MIME = "application/vnd.google-apps.folder"
_FOLDER_NAME = "Job Search Cockpit"
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"


class DriveApiError(ValueError):
    """Raised when a Drive response cannot prove the requested safe operation."""


@dataclass(frozen=True, slots=True)
class DriveFileMetadata:
    id: str
    name: str
    mime_type: str
    parents: tuple[str, ...]
    size: int | None
    sha256: str | None
    trashed: bool
    shared: bool
    app_authorized: bool


class DriveApiClient:
    """Makes only fixed, fail-closed Drive API requests."""

    def __init__(
        self,
        http_client: httpx.Client,
        finalisation_service: LocalResumeFinalisationService,
    ) -> None:
        self._http_client = http_client
        self._finalisation_service = finalisation_service

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

    def create_or_verify_folder(
        self, access_token: str, folder_id: str, *, before_request: Callable[[], None]
    ) -> DriveFileMetadata:
        if not 1 <= len(folder_id) <= 255:
            raise DriveApiError("The Drive folder identifier is invalid.")
        before_request()
        try:
            response = self._http_client.post(
                _FILES_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"id": folder_id, "name": _FOLDER_NAME, "mimeType": _FOLDER_MIME},
            )
        except httpx.HTTPError as error:
            raise DriveApiError("Google Drive is temporarily unavailable.") from error
        folder = self._metadata(response, "Google Drive did not create the private folder.")
        if (
            folder.id != folder_id
            or folder.name != _FOLDER_NAME
            or folder.mime_type != _FOLDER_MIME
            or folder.parents
            or folder.trashed
            or folder.shared
            or not folder.app_authorized
        ):
            raise DriveApiError("Google Drive did not verify the private folder.")
        return folder

    def reconcile_folder(
        self, access_token: str, folder_id: str, *, before_request: Callable[[], None]
    ) -> DriveFileMetadata | None:
        metadata = self._get_metadata(access_token, folder_id, before_request=before_request)
        if metadata is None:
            return None
        if (
            metadata.id != folder_id
            or metadata.name != _FOLDER_NAME
            or metadata.mime_type != _FOLDER_MIME
            or metadata.parents
            or metadata.trashed
            or metadata.shared
            or not metadata.app_authorized
        ):
            raise DriveApiError("Google Drive did not verify the private folder.")
        return metadata

    def reconcile_verified_file(
        self,
        access_token: str,
        file_id: str,
        *,
        final_artifact_id: str,
        file_kind: Literal["docx", "pdf"],
        folder_id: str,
        before_request: Callable[[], None],
    ) -> DriveFileMetadata | None:
        artifact = self._finalisation_service.artifact_by_id(final_artifact_id)
        metadata = self._get_metadata(access_token, file_id, before_request=before_request)
        if metadata is None:
            return None
        path, size, checksum, mime_type = self._expected_file(artifact, file_kind)
        if (
            metadata.id != file_id
            or metadata.name != path.name
            or metadata.mime_type != mime_type
            or metadata.parents != (folder_id,)
            or metadata.size != size
            or metadata.sha256 != checksum
            or metadata.trashed
            or metadata.shared
            or not metadata.app_authorized
        ):
            raise DriveApiError("Google Drive did not verify the final résumé file.")
        return metadata

    def upload_verified_file(
        self,
        *,
        access_token: str,
        file_id: str,
        folder_id: str,
        final_artifact_id: str,
        file_kind: Literal["docx", "pdf"],
        before_request: Callable[[], None],
    ) -> DriveFileMetadata:
        artifact = self._finalisation_service.artifact_by_id(final_artifact_id)
        if file_kind == "docx":
            path, size, checksum = (
                artifact.docx_path,
                artifact.docx_byte_length,
                artifact.docx_sha256,
            )
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            path, size, checksum = artifact.pdf_path, artifact.pdf_byte_length, artifact.pdf_sha256
            mime_type = "application/pdf"
        if (
            not path.is_file()
            or path.stat().st_size != size
            or sha256(path.read_bytes()).hexdigest() != checksum
            or not 1 <= len(file_id) <= 255
            or not 1 <= len(folder_id) <= 255
        ):
            raise DriveApiError("The verified final résumé file is unavailable.")
        before_request()
        initiated = self._http_client.post(
            _UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(size),
            },
            json={"id": file_id, "name": path.name, "mimeType": mime_type, "parents": [folder_id]},
        )
        session_url = initiated.headers.get("Location") if initiated.status_code == 200 else ""
        parsed = urlsplit(session_url)
        if parsed.scheme != "https" or parsed.hostname != _DRIVE_API_HOST:
            raise DriveApiError("Google Drive did not provide a valid upload session.")
        before_request()
        uploaded = self._http_client.put(
            session_url,
            headers={"Content-Type": mime_type, "Content-Length": str(size)},
            content=path.read_bytes(),
        )
        metadata = self._metadata(uploaded, "Google Drive did not verify the final résumé file.")
        if (
            metadata.id != file_id
            or metadata.name != path.name
            or metadata.mime_type != mime_type
            or metadata.parents != (folder_id,)
            or metadata.size != size
            or metadata.sha256 != checksum
            or metadata.trashed
            or metadata.shared
            or not metadata.app_authorized
        ):
            raise DriveApiError("Google Drive did not verify the final résumé file.")
        return metadata

    def _get_metadata(
        self, access_token: str, file_id: str, *, before_request: Callable[[], None]
    ) -> DriveFileMetadata | None:
        if not 1 <= len(file_id) <= 255 or not 1 <= len(access_token) <= 4096:
            raise DriveApiError("The Drive request is invalid.")
        before_request()
        try:
            response = self._http_client.get(
                f"{_FILES_URL}/{quote(file_id, safe='')}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as error:
            raise DriveApiError("Google Drive is temporarily unavailable.") from error
        if response.status_code == 404:
            return None
        return self._metadata(response, "Google Drive did not verify the backup file.")

    @staticmethod
    def _expected_file(
        artifact: FinalResumeArtifact, file_kind: Literal["docx", "pdf"]
    ) -> tuple[Path, int, str, str]:
        if file_kind == "docx":
            return (
                artifact.docx_path,
                artifact.docx_byte_length,
                artifact.docx_sha256,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        return artifact.pdf_path, artifact.pdf_byte_length, artifact.pdf_sha256, "application/pdf"

    @staticmethod
    def _metadata(response: httpx.Response, failure: str) -> DriveFileMetadata:
        if response.status_code not in {200, 201}:
            raise DriveApiError(failure)
        try:
            payload = response.json()
        except ValueError as error:
            raise DriveApiError("The Google Drive response is invalid.") from error
        if not isinstance(payload, dict):
            raise DriveApiError("The Google Drive response is invalid.")
        identifier = payload.get("id")
        name = payload.get("name")
        mime_type = payload.get("mimeType")
        parents = payload.get("parents", [])
        size = payload.get("size")
        checksum = payload.get("sha256Checksum")
        flags = (payload.get("trashed"), payload.get("shared"), payload.get("isAppAuthorized"))
        if (
            not all(isinstance(value, str) and value for value in (identifier, name, mime_type))
            or not isinstance(parents, list)
            or any(not isinstance(parent, str) or not parent for parent in parents)
            or (size is not None and (not isinstance(size, str) or not size.isdigit()))
            or (checksum is not None and (not isinstance(checksum, str) or len(checksum) != 64))
            or not all(isinstance(value, bool) for value in flags)
        ):
            raise DriveApiError("The Google Drive response is invalid.")
        assert isinstance(identifier, str)
        assert isinstance(name, str)
        assert isinstance(mime_type, str)
        assert isinstance(flags[0], bool)
        assert isinstance(flags[1], bool)
        assert isinstance(flags[2], bool)
        return DriveFileMetadata(
            id=identifier,
            name=name,
            mime_type=mime_type,
            parents=tuple(parents),
            size=int(size) if size is not None else None,
            sha256=checksum,
            trashed=flags[0],
            shared=flags[1],
            app_authorized=flags[2],
        )
