import pytest

from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.discovery import DiscoveryService
from job_search_cockpit.phase2.types import Phase2ActivationUnavailable


def test_discovery_is_denied_when_phase_two_activation_is_unavailable(
    phase2_settings: Phase2Settings,
) -> None:
    service = DiscoveryService.unavailable_for_tests(phase2_settings)

    with pytest.raises(Phase2ActivationUnavailable, match="provider access is unavailable"):
        service.run_micro_pilot()
