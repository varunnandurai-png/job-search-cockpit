import json
from pathlib import Path

import httpx

from job_search_cockpit.phase2.drive_api import DriveApiClient
from job_search_cockpit.phase2.finalisation import FINALISE_CONFIRMATION, FinaliseResumeCommand
from tests.support.phase3 import build_synthetic_phase3_runtime


def test_generate_ids_uses_the_exact_drive_endpoint(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ids": ["folder-1", "docx-1", "pdf-1"]})

    client = DriveApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)), runtime.service
    )

    ids = client.generate_ids("short-lived-access", 3, before_request=lambda: None)

    assert ids == ("folder-1", "docx-1", "pdf-1")
    assert str(requests[0].url) == (
        "https://www.googleapis.com/drive/v3/files/generateIds?count=3&space=drive&type=files"
    )
    assert requests[0].headers["Authorization"] == "Bearer short-lived-access"
    runtime.close()


def test_create_folder_uses_the_reserved_id_and_private_folder_mime_type(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "folder-1",
                "name": "Job Search Cockpit",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [],
                "trashed": False,
                "shared": False,
                "isAppAuthorized": True,
            },
        )

    client = DriveApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)), runtime.service
    )

    folder = client.create_or_verify_folder(
        "short-lived-access", "folder-1", before_request=lambda: None
    )

    assert folder.id == "folder-1"
    assert folder.name == "Job Search Cockpit"
    assert str(requests[0].url) == "https://www.googleapis.com/drive/v3/files"
    assert json.loads(requests[0].content) == {
        "id": "folder-1",
        "name": "Job Search Cockpit",
        "mimeType": "application/vnd.google-apps.folder",
    }
    runtime.close()


def test_upload_uses_exact_id_parent_name_and_mime(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    review = runtime.service.start_review("job-1")
    artifact = runtime.service.finalise(
        FinaliseResumeCommand(review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path)
    )
    source = artifact.docx_path
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                headers={"Location": "https://www.googleapis.com/upload-session/docx-1"},
            )
        return httpx.Response(
            200,
            json={
                "id": "docx-1",
                "name": source.name,
                "mimeType": (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                "parents": ["folder-1"],
                "size": str(source.stat().st_size),
                "sha256Checksum": artifact.docx_sha256,
                "trashed": False,
                "shared": False,
                "isAppAuthorized": True,
            },
        )

    client = DriveApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        runtime.service,
    )
    result = client.upload_verified_file(
        access_token="short-lived-access",
        file_id="docx-1",
        folder_id="folder-1",
        final_artifact_id=artifact.artifact_id,
        file_kind="docx",
        before_request=lambda: None,
    )

    assert result.id == "docx-1"
    assert result.parents == ("folder-1",)
    assert [request.method for request in requests] == ["POST", "PUT"]
    runtime.close()


def test_retry_reconciles_only_the_reserved_file_id(tmp_path: Path) -> None:
    runtime = build_synthetic_phase3_runtime(tmp_path)
    review = runtime.service.start_review("job-1")
    artifact = runtime.service.finalise(
        FinaliseResumeCommand(review.attempt_id, FINALISE_CONFIRMATION, runtime.headshot_path)
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "docx-1",
                "name": artifact.docx_path.name,
                "mimeType": (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                "parents": ["folder-1"],
                "size": str(artifact.docx_byte_length),
                "sha256Checksum": artifact.docx_sha256,
                "trashed": False,
                "shared": False,
                "isAppAuthorized": True,
            },
        )

    client = DriveApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)), runtime.service
    )
    result = client.reconcile_verified_file(
        "short-lived-access",
        "docx-1",
        final_artifact_id=artifact.artifact_id,
        file_kind="docx",
        folder_id="folder-1",
        before_request=lambda: None,
    )

    assert result is not None
    assert str(requests[0].url) == "https://www.googleapis.com/drive/v3/files/docx-1"
    runtime.close()
