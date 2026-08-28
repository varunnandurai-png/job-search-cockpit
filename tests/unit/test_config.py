import os
from hashlib import sha256
from pathlib import Path

import pytest

from job_search_cockpit.config import Settings, SourceKind, SourceSpec
from job_search_cockpit.sources import UnsafeSourceError, safe_open_source


def test_default_settings_keep_private_data_outside_repository() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.data_dir == Path.home() / "Library/Application Support/JobSearchCockpit"
    assert settings.database_path == settings.data_dir / "vault.sqlite3"


def test_google_client_id_is_validated_public_environment_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID",
        "123.apps.googleusercontent.com",
    )

    settings = Settings.from_environment(data_dir=tmp_path)

    assert settings.google_oauth_client_id == "123.apps.googleusercontent.com"


def test_google_client_id_can_be_loaded_from_the_local_dotenv_without_overriding_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID=456.apps.googleusercontent.com\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID", raising=False)

    assert Settings.from_environment(data_dir=tmp_path).google_oauth_client_id == (
        "456.apps.googleusercontent.com"
    )


def test_curated_source_manifest_is_exact() -> None:
    settings = Settings()
    assert [source.key for source in settings.sources] == [
        "assessment",
        "profile_json",
        "master_profile",
        "resume_workflow",
    ]
    assert all(source.read_only for source in settings.sources)


def test_test_settings_never_resolve_to_live_sources(vault_settings: Settings) -> None:
    live_root = Path("/Users/nandurivarun/Desktop/Documents/CV").resolve()
    assert all(
        not source.path.resolve().is_relative_to(live_root) for source in vault_settings.sources
    )


def test_safe_open_source_returns_descriptor_derived_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "source.md"
    content = b"Trusted fixture\n"
    source_path.write_bytes(content)
    source = safe_open_source(SourceSpec("fixture", SourceKind.ASSESSMENT, source_path))

    source_stat = os.stat(source_path)
    assert source.content == content
    assert source.content_hash == sha256(content).hexdigest()
    assert source.device == source_stat.st_dev
    assert source.inode == source_stat.st_ino
    assert source.size == len(content)


def test_safe_open_source_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("private", encoding="utf-8")
    link = tmp_path / "source.md"
    link.symlink_to(target)

    with pytest.raises(UnsafeSourceError, match="symbolic link"):
        safe_open_source(SourceSpec("fixture", SourceKind.ASSESSMENT, link))
