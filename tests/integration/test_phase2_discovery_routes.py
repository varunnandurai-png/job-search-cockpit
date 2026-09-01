from dataclasses import dataclass
from datetime import UTC, datetime

from job_search_cockpit.phase2.assessment_types import ConfidenceState, GateResult
from job_search_cockpit.phase2.candidates import CandidateReview
from job_search_cockpit.phase2.discovery import DiscoveryResult, DiscoveryStatusView
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.ports import PreparedVault
from tests.support.web import authenticated_test_app


@dataclass(slots=True)
class _DiscoveryService:
    ran: bool = False

    def run_micro_pilot(self) -> DiscoveryResult:
        self.ran = True
        return DiscoveryResult("run-1", {"fixture": 1}, 1, 1)

    def status_view(self) -> DiscoveryStatusView:
        return DiscoveryStatusView(
            provider_configuration_available=True,
            last_run_at=datetime.now(UTC) if self.ran else None,
            last_run_counts={"fixture": 1} if self.ran else {},
            candidate_count=1 if self.ran else 0,
            verification_count=0,
        )


@dataclass(slots=True)
class _CandidateWorkflowService:
    def current_candidates(self) -> tuple[CandidateReview, ...]:
        return (
            CandidateReview(
                job_revision_id="eligible",
                title="Senior Product Manager",
                employer_name="Example Employer",
                locations=("Hyderabad",),
                gate_result=GateResult.PASS,
                gate_reason_codes=("profile_gate_pass",),
                confidence=ConfidenceState.HIGH,
                current=True,
            ),
            CandidateReview(
                job_revision_id="ineligible",
                title="Unapproved role",
                employer_name="Other Employer",
                locations=("Remote",),
                gate_result=GateResult.FAIL,
                gate_reason_codes=("no_eligible_location",),
                confidence=ConfidenceState.BLOCKED,
                current=True,
            ),
        )


def _configure(prepared: PreparedVault) -> None:
    runtime = prepared.phase2_runtime
    assert isinstance(runtime, Phase2Runtime)
    runtime.discovery_service = _DiscoveryService()  # type: ignore[assignment]
    runtime.candidate_workflow_service = _CandidateWorkflowService()  # type: ignore[assignment]


def _candidate_button_fragment(page: str, candidate_id: str) -> str:
    return page.split(f'data-candidate="{candidate_id}"', maxsplit=1)[1].split("</article>", 1)[0]


def test_manual_discovery_requires_csrf_and_renders_real_candidate(vault_settings) -> None:
    with authenticated_test_app(vault_settings, configure_prepared=_configure) as app:
        assert app.client.post("/phase-2/discovery-runs").status_code == 403
        response = app.post("/phase-2/discovery-runs", data={}, follow_redirects=False)
        page = app.get("/phase-2/review")

    assert response.status_code == 303
    assert "Senior Product Manager" in page.text
    assert "Map approved evidence" in page.text
    assert "Verify selected candidate" not in _candidate_button_fragment(page.text, "eligible")


def test_ineligible_candidate_has_no_verification_form(vault_settings) -> None:
    with authenticated_test_app(vault_settings, configure_prepared=_configure) as app:
        page = app.get("/phase-2/review")

    assert 'data-candidate="ineligible"' in page.text
    assert "Eligibility must be resolved" in _candidate_button_fragment(page.text, "ineligible")
