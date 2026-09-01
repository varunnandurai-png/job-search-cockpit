from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from job_search_cockpit.phase2.assessment_types import (
    ConfidenceState,
    EvidenceRelation,
    GateResult,
    Requirement,
    RequirementKind,
    ScoringComponent,
)
from job_search_cockpit.phase2.candidates import CandidateReview
from job_search_cockpit.phase2.discovery import DiscoveryResult, DiscoveryStatusView
from job_search_cockpit.phase2.models import (
    Phase2DiscoveryRun,
    Phase2JobRecord,
    Phase2JobRevision,
    Phase2JobVerification,
    Phase2ResumeRequirementLedger,
    Phase2SourceListingObservation,
)
from job_search_cockpit.phase2.resume_safety import (
    ResumePreparationError,
    VerifiedJobPreparationAuthorization,
)
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.ports import PreparedVault
from job_search_cockpit.web.routes.phase2 import _mapping_selections
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


@dataclass(slots=True)
class _DurablePreparationPort:
    runtime: Phase2Runtime
    mismatch: bool = False

    def authorization_for_resume(self, job_id: str) -> VerifiedJobPreparationAuthorization:
        with self.runtime.coordinator._session_factory() as session:
            verification = session.get(Phase2JobVerification, "verification-1")
            ledger = session.get(Phase2ResumeRequirementLedger, "ledger-1")
        if verification is None or ledger is None:
            raise ResumePreparationError("not current")
        expires_at = verification.expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise ResumePreparationError("not current")
        return VerifiedJobPreparationAuthorization(
            job_id=job_id,
            job_revision_id="other-revision" if self.mismatch else verification.job_revision_id,
            selected_location_path_fingerprint=verification.selected_location_path_fingerprint,
            authorization_id=verification.authorization_id,
            authorization_nonce=verification.authorization_nonce,
            eligibility="eligible",
            expires_at=expires_at,
            phase1_profile_fingerprint=verification.phase1_profile_fingerprint,
            phase1_profile_generation=verification.phase1_profile_generation,
            phase1_readiness_fingerprint=verification.phase1_readiness_fingerprint,
            phase1_readiness_generation=verification.phase1_readiness_generation,
            phase1_authority_fingerprint=verification.phase1_authority_fingerprint,
            phase1_authority_generation=verification.phase1_authority_generation,
            phase1_restore_generation=verification.phase1_restore_generation,
            phase2_activation_generation=verification.phase2_activation_generation,
            phase2_restore_generation=verification.phase2_restore_generation,
            requirement_ids=tuple(str(item) for item in ledger.requirement_ids_json),
            requirement_ledger_fingerprint=ledger.requirement_ledger_fingerprint,
            company_name="Example Employer",
            role_name="Senior Product Manager",
        )


def _configure(prepared: PreparedVault) -> None:
    runtime = prepared.phase2_runtime
    assert isinstance(runtime, Phase2Runtime)
    runtime.discovery_service = _DiscoveryService()  # type: ignore[assignment]
    runtime.candidate_workflow_service = _CandidateWorkflowService()  # type: ignore[assignment]


def _configure_durable_resume(
    prepared: PreparedVault, *, expired: bool = False, mismatch: bool = False
) -> None:
    _configure(prepared)
    runtime = prepared.phase2_runtime
    assert isinstance(runtime, Phase2Runtime)

    def seed(session: object) -> None:
        if session.get(Phase2JobRecord, "stable-job") is not None:  # type: ignore[union-attr]
            return
        fields = {
            "phase1_profile_fingerprint": "a" * 64,
            "phase1_profile_generation": 1,
            "phase1_readiness_fingerprint": "b" * 64,
            "phase1_readiness_generation": 1,
            "phase1_authority_fingerprint": "c" * 64,
            "phase1_authority_generation": 1,
            "phase1_restore_generation": 0,
            "phase2_activation_generation": 1,
            "phase2_restore_generation": 0,
        }
        session.add(Phase2DiscoveryRun(id="run-1", **fields))  # type: ignore[union-attr]
        session.flush()  # type: ignore[union-attr]
        session.add(  # type: ignore[union-attr]
            Phase2SourceListingObservation(
                id="source-1", discovery_run_id="run-1", provider_id="test",
                provider_run_id=None, source_listing_id="listing-1",
                canonical_url="https://example.test/job", title="Senior Product Manager",
                employer_name="Example Employer", locations_json=["Hyderabad"], posted_at=None,
                public_description="public", compensation_text=None, retrieved_at=datetime.now(UTC),
                raw_content_fingerprint="i" * 64, content_fingerprint="g" * 64,
            )
        )
        session.add(Phase2JobRecord(id="stable-job", posting_identity_fingerprint="d" * 64))  # type: ignore[union-attr]
        session.flush()  # type: ignore[union-attr]
        session.add(  # type: ignore[union-attr]
            Phase2JobRevision(
                id="eligible", job_record_id="stable-job", source_observation_id="source-1",
                canonical_url="https://example.test/job", title="Senior Product Manager",
                employer_name="Example Employer", locations_json=["Hyderabad"], posted_at=None,
                public_description="public", compensation_text=None, content_fingerprint="e" * 64,
            )
        )
        session.add(  # type: ignore[union-attr]
            Phase2JobVerification(
                id="verification-1", authorization_id="auth-1", authorization_nonce="nonce-1",
                job_revision_id="eligible", selected_location_path_fingerprint="f" * 64,
                source_observation_fingerprint="g" * 64,
                expires_at=(
                    datetime.now(UTC) - timedelta(seconds=1)
                    if expired
                    else datetime.now(UTC) + timedelta(hours=1)
                ),
                **fields,
            )
        )
        session.add(  # type: ignore[union-attr]
            Phase2ResumeRequirementLedger(
                id="ledger-1", job_id="stable-job", job_revision_id="eligible",
                requirement_ids_json=["skills.product_management"],
                requirement_ledger_fingerprint="h" * 64,
                phase2_activation_generation=1, phase2_restore_generation=0,
            )
        )

    runtime.coordinator.run(seed, "seed_durable_resume_action")
    runtime.verified_job_preparation_port = _DurablePreparationPort(runtime, mismatch)  # type: ignore[assignment]


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


def test_durable_verified_candidate_renders_resume_action_after_fresh_runtime(
    vault_settings,
) -> None:
    with authenticated_test_app(
        vault_settings, configure_prepared=_configure_durable_resume
    ) as app:
        first = app.get("/phase-2/review")

    with authenticated_test_app(
        vault_settings, configure_prepared=_configure_durable_resume
    ) as app:
        restarted = app.get("/phase-2/review")

    for page in (first, restarted):
        fragment = _candidate_button_fragment(page.text, "eligible")
        assert "Prepare tailored résumé" in fragment
        assert 'action="/phase-2/resume-reviews"' in fragment
        assert 'name="job_id" value="stable-job"' in fragment


@pytest.mark.parametrize("expired,mismatch", ((True, False), (False, True)))
def test_expired_or_mismatched_durable_authorization_hides_resume_action(
    vault_settings, expired: bool, mismatch: bool
) -> None:
    def configure(prepared: PreparedVault) -> None:
        _configure_durable_resume(prepared, expired=expired, mismatch=mismatch)

    with authenticated_test_app(vault_settings, configure_prepared=configure) as app:
        page = app.get("/phase-2/review")

    assert "Prepare tailored résumé" not in _candidate_button_fragment(page.text, "eligible")


@pytest.mark.parametrize("choice", ("-1", "word", "3"))
def test_mapping_selection_rejects_noncanonical_or_out_of_range_choice(choice: str) -> None:
    launch = SimpleNamespace(
        requirements=(
            Requirement(
                "skills.product_management",
                RequirementKind.REQUIRED,
                ScoringComponent.EVIDENCE,
                "span-1",
                0,
                10,
            ),
        ),
        choices=(("key", "claim", "revision", "support", "safe wording"),),
    )

    with pytest.raises(ValueError):
        _mapping_selections(
            launch,
            {
                "relation:skills.product_management": EvidenceRelation.DIRECT.value,
                "reason:skills.product_management": "direct/exact_capability_performed",
                "choice:skills.product_management": choice,
            },
        )


def test_disclosure_budget_is_authenticated_no_store_and_renewal_rejects_wrong_confirmation(
    vault_settings,
) -> None:
    with authenticated_test_app(vault_settings, configure_prepared=_configure) as app:
        page = app.get("/phase-2/disclosure-budget")
        rejected = app.post(
            "/phase-2/disclosure-epochs",
            data={"reason": "reviewed", "confirmation": "wrong"},
            follow_redirects=False,
        )
        after = app.get("/phase-2/disclosure-budget")

    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "Current epoch" in page.text
    assert rejected.status_code == 303
    assert "Current epoch" in after.text
