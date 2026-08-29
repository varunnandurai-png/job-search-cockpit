import pytest

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.resume_safety import ResumePreparationError
from job_search_cockpit.phase2.types import Phase2ActivationUnavailable
from job_search_cockpit.phase2.verification import CatalogVerifiedJobPreparationPort


def test_discovery_is_denied_when_phase_two_activation_is_unavailable(
    phase2_settings: Phase2Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    service = DiscoveryService.unavailable_for_tests(phase2_settings)

    status = service.status_view()

    assert status.provider_configuration_status == "missing"
    assert status.provider_failures == {}
    with pytest.raises(Phase2ActivationUnavailable, match="provider access is unavailable"):
        service.run_micro_pilot()


def test_unverified_discovery_cannot_authorize_resume_preparation(
    phase2_settings: Phase2Settings,
) -> None:
    port = CatalogVerifiedJobPreparationPort.unavailable(phase2_settings)

    with pytest.raises(ResumePreparationError, match="verified job readiness is unavailable"):
        port.authorization_for_resume("unknown-job")
