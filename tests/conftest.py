import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from job_search_cockpit.config import Settings, SourceSpec
from job_search_cockpit.phase2.config import Phase2Settings
from tests.support.builders import FixedClock


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.for_tests(tmp_path / "data", tmp_path / "sources")


@pytest.fixture
def phase2_settings(tmp_path: Path) -> Phase2Settings:
    return Phase2Settings(data_dir=tmp_path / "data")


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def launch_session_id() -> str:
    return "sanitized-launch-session"


@pytest.fixture
def vault_settings(tmp_path: Path) -> Iterator[Settings]:
    source_root = tmp_path / "sources"
    (source_root / "Context").mkdir(parents=True)
    profile_bank = source_root / "Old Data" / "profile_bank"
    profile_bank.mkdir(parents=True)

    fixture_root = Path(__file__).parent / "fixtures" / "sources"
    fixture_map = {
        "assessment.md": source_root / "Context" / "job-search-profile-assessment.md",
        "profile.json": profile_bank / "profile.json",
        "master_profile.md": profile_bank / "Varun_Nanduri_Master_Profile.md",
        "resume_workflow.md": profile_bank / "Varun_Nanduri_Resume_Workflow.md",
    }
    for source_name, destination in fixture_map.items():
        fixture = fixture_root / source_name
        if fixture.exists():
            shutil.copyfile(fixture, destination)
        else:
            destination.write_text("Sanitized test fixture\n", encoding="utf-8")

    settings = Settings.for_tests(data_dir=tmp_path / "data", source_root=source_root)
    yield settings

    live_data = Path.home() / "Library/Application Support/JobSearchCockpit"
    assert not settings.data_dir.resolve().is_relative_to(live_data.resolve())
    live_sources = Path("/Users/nandurivarun/Desktop/Documents/CV").resolve()
    assert all(
        not source.path.resolve().is_relative_to(live_sources) for source in settings.sources
    )


def _source(settings: Settings, key: str) -> SourceSpec:
    return next(source for source in settings.sources if source.key == key)


@pytest.fixture
def assessment_spec(vault_settings: Settings) -> SourceSpec:
    return _source(vault_settings, "assessment")


@pytest.fixture
def profile_json_spec(vault_settings: Settings) -> SourceSpec:
    return _source(vault_settings, "profile_json")


@pytest.fixture
def master_profile_spec(vault_settings: Settings) -> SourceSpec:
    return _source(vault_settings, "master_profile")


@pytest.fixture
def resume_workflow_spec(vault_settings: Settings) -> SourceSpec:
    return _source(vault_settings, "resume_workflow")


@pytest.fixture
def sanitized_source_specs(vault_settings: Settings) -> tuple[SourceSpec, ...]:
    return tuple(vault_settings.sources)
