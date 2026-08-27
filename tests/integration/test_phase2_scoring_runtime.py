import pytest

from job_search_cockpit.phase2.assessment import (
    AssessmentAuthorityService,
    AssessmentUnavailable,
)
from job_search_cockpit.phase2.types import ActivationCommand
from tests.integration.test_phase2_activation import _service
from tests.support.web import authenticated_test_app


def test_assessment_publication_rejects_phase1_drift_after_authority_capture(
    phase2_settings,
) -> None:
    with _service(phase2_settings) as (activation_service, phase1_port):
        activation_service.activate(
            ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II")
        )
        authority_service = AssessmentAuthorityService(phase1_port, activation_service)
        captured = authority_service.capture_for_assessment()
        phase1_port.current = phase1_port.current.model_copy(
            update={
                "readiness": phase1_port.current.readiness.model_copy(
                    update={"readiness_generation": 2}
                )
            }
        )

        with pytest.raises(AssessmentUnavailable, match="authority changed"):
            authority_service.revalidate_before_publication(captured)


def test_assessment_view_is_authenticated_and_redacted_without_current_authority(
    vault_settings,
) -> None:
    with authenticated_test_app(vault_settings) as client:
        response = client.get("/phase-2/assessments")

    assert response.status_code == 200
    assert "Current match assessments are unavailable." in response.text
    assert "safe wording" not in response.text.lower()
