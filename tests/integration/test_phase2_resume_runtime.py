import pytest

from job_search_cockpit.config import Settings
from job_search_cockpit.phase2.resume_safety import ResumePreparationError
from job_search_cockpit.phase2.runtime import prepare_phase2_runtime


class _Phase1Port:
    def activation_inputs(self) -> object:
        raise AssertionError("Runtime setup must not request Phase I inputs.")

    def revalidate_activation_inputs(self, expected: object) -> object:
        raise AssertionError("Runtime setup must not revalidate Phase I inputs.")


def test_runtime_denies_resume_preparation_without_verified_job_readiness(
    phase2_settings,
    tmp_path,
) -> None:
    settings = Settings.for_tests(phase2_settings.data_dir, tmp_path / "sanitized-sources")
    runtime = prepare_phase2_runtime(settings, _Phase1Port())
    try:
        with pytest.raises(ResumePreparationError, match="verified job readiness is unavailable"):
            runtime.resume_preparation_service.start(
                job_id="sanitized-job-1", resume_kind="tailored"
            )
    finally:
        runtime.close()


def test_default_runtime_has_no_enabled_official_provider_instance(
    phase2_settings,
    tmp_path,
) -> None:
    settings = Settings.for_tests(phase2_settings.data_dir, tmp_path / "sanitized-sources")
    runtime = prepare_phase2_runtime(settings, _Phase1Port())
    try:
        assert runtime.discovery_service.status_view().provider_configuration_available is False
    finally:
        runtime.close()


def test_drive_backup_runtime_is_disabled_without_a_client_id(
    phase2_settings,
    tmp_path,
) -> None:
    settings = Settings.for_tests(phase2_settings.data_dir, tmp_path / "sanitized-sources")
    runtime = prepare_phase2_runtime(settings, _Phase1Port())
    try:
        assert runtime.drive_backup_service is None
    finally:
        runtime.close()
