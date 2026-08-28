from urllib.parse import parse_qs, urlsplit

from job_search_cockpit.phase2.drive_auth import DriveAuthorizationService

LOOPBACK_URI = "http://127.0.0.1:8765/phase-2/drive-backups/oauth/callback"


def test_begin_uses_exact_scope_s256_state_and_loopback() -> None:
    service = DriveAuthorizationService(client_id="desktop-client-id")

    request = service.begin(
        operation_id="operation-1",
        session_id="launch-session-1",
        redirect_uri=LOOPBACK_URI,
    )

    query = parse_qs(urlsplit(request.authorization_url).query)
    assert urlsplit(request.authorization_url)._replace(query="").geturl() == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [LOOPBACK_URI]
    assert len(query["state"][0]) >= 43
