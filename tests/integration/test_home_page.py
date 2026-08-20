from tests.support.database import count_rows
from tests.support.web import build_test_app


def test_home_shows_plain_language_readiness_and_single_primary_action(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        response = client.get("/")
        assert response.status_code == 200
        assert "Not ready for Phase 2" in response.text
        assert "Import curated profile" in response.text
        assert response.text.count('class="button button--primary"') == 1


def test_import_preview_is_read_only_then_matching_preview_can_apply(vault_settings):
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        preview = client.post(
            "/imports/preview",
            headers={"origin": "http://127.0.0.1:8765"},
            data={"csrf_token": launch.csrf_token},
        )
        assert preview.status_code == 200
        assert "Original files remain unchanged" in preview.text
        assert preview.text.count("Ready") >= 4
        assert count_rows(vault_settings.database_path, "claims") == 0
        preview_id = preview.headers["x-preview-id"]

        applied = client.post(
            "/imports/apply",
            headers={"origin": "http://127.0.0.1:8765"},
            data={"csrf_token": launch.csrf_token, "preview_id": preview_id},
            follow_redirects=False,
        )
        assert applied.status_code == 303
        assert count_rows(vault_settings.database_path, "claims") > 0


def test_imported_html_like_text_is_escaped(vault_settings):
    source = vault_settings.sources[3].path
    source.write_text(
        source.read_text(encoding="utf-8") + "\n- <script>alert('fixture')</script>\n",
        encoding="utf-8",
    )
    with build_test_app(vault_settings) as (launch, client):
        client.get(f"/launch?token={launch.token}")
        response = client.post(
            "/imports/preview",
            headers={"origin": "http://127.0.0.1:8765"},
            data={"csrf_token": launch.csrf_token},
        )
        assert "<script>" not in response.text
