import time
from datetime import UTC, datetime

from job_search_cockpit.web.security import LaunchSession
from tests.support.web import build_test_app, parse_set_cookie


def test_protected_page_requires_launch_session(vault_settings):
    with build_test_app(vault_settings) as (_launch, client):
        response = client.get("/")
        assert response.status_code == 401


def test_launch_token_is_exchanged_for_process_session_cookie(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        response = client.get(f"/launch?token={launch.token}", follow_redirects=False)
        assert response.status_code == 303
        cookie = parse_set_cookie(response.headers["set-cookie"])
        assert cookie.httponly is True
        assert cookie.samesite.lower() == "strict"
        assert cookie.path == "/"
        assert launch.token not in response.headers["location"]
        assert client.get(f"/launch?token={launch.token}").status_code == 401


def test_wrong_host_cookie_tampering_and_missing_csrf_are_rejected(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        assert client.get("/", headers={"host": "localhost:8765"}).status_code == 400
        cookie = client.cookies.get("cockpit_session")
        assert cookie is not None
        client.cookies.set("cockpit_session", f"{cookie}tampered")
        assert client.get("/").status_code == 401

    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        response = client.post("/imports/preview", headers={"origin": "http://127.0.0.1:8765"})
        assert response.status_code == 403


def test_launch_token_uses_monotonic_five_minute_boundary(vault_settings):
    launch = LaunchSession(
        token="fixture-token",
        cookie_secret="cookie-secret",
        csrf_secret="csrf-secret",
        issued_at=datetime.now(UTC),
        monotonic_deadline=time.monotonic() - 0.001,
        consumed=False,
    )
    with build_test_app(vault_settings, launch=launch) as (_launch, client):
        assert client.get("/launch?token=fixture-token").status_code == 401


def test_security_headers_are_on_private_responses(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        response = client.get("/")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_process_restart_invalidates_cookie(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        old_cookie = client.cookies.get("cockpit_session")
    assert old_cookie is not None
    with build_test_app(vault_settings) as (_launch, client):
        client.cookies.set("cockpit_session", old_cookie)
        assert client.get("/").status_code == 401


def test_foreign_origin_and_unsupported_method_are_rejected(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        assert (
            client.post(
                "/imports/preview",
                headers={"origin": "https://attacker.example"},
                data={"csrf_token": launch.csrf_token},
            ).status_code
            == 403
        )
        assert client.put("/").status_code == 405
