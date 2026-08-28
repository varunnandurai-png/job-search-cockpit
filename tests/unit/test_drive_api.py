import json

import httpx

from job_search_cockpit.phase2.drive_api import DriveApiClient


def test_generate_ids_uses_the_exact_drive_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ids": ["folder-1", "docx-1", "pdf-1"]})

    client = DriveApiClient(httpx.Client(transport=httpx.MockTransport(handler)))

    ids = client.generate_ids("short-lived-access", 3, before_request=lambda: None)

    assert ids == ("folder-1", "docx-1", "pdf-1")
    assert str(requests[0].url) == (
        "https://www.googleapis.com/drive/v3/files/generateIds?count=3&space=drive&type=files"
    )
    assert requests[0].headers["Authorization"] == "Bearer short-lived-access"


def test_create_folder_uses_the_reserved_id_and_private_folder_mime_type() -> None:
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

    client = DriveApiClient(httpx.Client(transport=httpx.MockTransport(handler)))

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
