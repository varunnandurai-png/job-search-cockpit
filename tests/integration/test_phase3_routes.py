from dataclasses import dataclass
from pathlib import Path

from job_search_cockpit.phase2.finalisation import (
    FINALISE_CONFIRMATION,
    FinalisationError,
    FinaliseResumeCommand,
    FinalResumeArtifact,
    ResumeDocumentReview,
)
from job_search_cockpit.phase2.requirements import (
    RequirementLedger,
    SupportedRequirement,
)
from job_search_cockpit.phase2.runtime import Phase2Runtime
from job_search_cockpit.ports import PreparedVault
from job_search_cockpit.web.routes.phase2 import router as phase2_router
from tests.support.web import authenticated_test_app, build_test_app


@dataclass(slots=True)
class SyntheticRouteFinalisationService:
    tmp_path: Path
    finalised: bool = False

    def _review(self) -> ResumeDocumentReview:
        return ResumeDocumentReview(
            attempt_id="attempt-1",
            job_id="job-1",
            job_revision_id="job-revision-1",
            plain_text="Varun Resume\n\nSelected Experience\n\nBuilt Python services.",
            content_fingerprint="a" * 64,
            requirements=RequirementLedger(
                projection_fingerprint="b" * 64,
                supported=(
                    SupportedRequirement(
                        requirement_id="skills.python",
                        claim_id="claim-1",
                        revision_id="fact-revision-1",
                        support_assertion_id="support-1",
                        safe_wording="Built Python services.",
                        employer_key=None,
                        period_start=None,
                        period_end=None,
                    ),
                ),
                unsupported=(),
            ),
            exact_confirmation=FINALISE_CONFIRMATION,
        )

    def start_review(self, job_id: str) -> ResumeDocumentReview:
        if job_id != "job-1":
            raise FinalisationError("Synthetic secret detail must not be displayed.")
        return self._review()

    def review_for(self, attempt_id: str) -> ResumeDocumentReview:
        if attempt_id != "attempt-1":
            raise FinalisationError("Synthetic secret detail must not be displayed.")
        return self._review()

    def finalise(self, command: FinaliseResumeCommand) -> FinalResumeArtifact:
        if command.confirmation != FINALISE_CONFIRMATION:
            raise FinalisationError("Type the exact finalisation confirmation.")
        if command.attempt_id != "attempt-1" or not command.headshot_path.is_file():
            raise FinalisationError("Synthetic secret detail must not be displayed.")
        self.finalised = True
        return self._artifact()

    def artifacts_for(self, attempt_id: str) -> FinalResumeArtifact:
        if attempt_id != "attempt-1" or not self.finalised:
            raise FinalisationError("The final résumé artifacts are unavailable.")
        return self._artifact()

    def _artifact(self) -> FinalResumeArtifact:
        return FinalResumeArtifact(
            attempt_id="attempt-1",
            job_id="job-1",
            job_revision_id="job-revision-1",
            docx_path=self.tmp_path / "Varun_Resume_Acme.docx",
            docx_sha256="c" * 64,
            docx_byte_length=123,
            pdf_path=self.tmp_path / "Varun_Resume_Acme.pdf",
            pdf_sha256="d" * 64,
            pdf_byte_length=456,
            content_fingerprint="a" * 64,
        )


def _configure(service: SyntheticRouteFinalisationService):
    def configure(prepared: PreparedVault) -> None:
        runtime = prepared.phase2_runtime
        assert isinstance(runtime, Phase2Runtime)
        runtime.resume_finalisation_service = service  # type: ignore[assignment]

    return configure


def test_phase3_routes_require_authentication_origin_and_csrf(
    vault_settings, tmp_path: Path
) -> None:
    service = SyntheticRouteFinalisationService(tmp_path)
    configure = _configure(service)
    with build_test_app(vault_settings, configure_prepared=configure) as (_launch, client):
        assert client.get("/phase-2/resume-reviews/attempt-1").status_code == 401

    with authenticated_test_app(vault_settings, configure_prepared=configure) as client:
        missing_csrf = client.client.post(
            "/phase-2/resume-reviews",
            data={"job_id": "job-1"},
            headers={"origin": client.origin},
        )
        foreign_origin = client.client.post(
            "/phase-2/resume-reviews",
            data={"job_id": "job-1", "csrf_token": client.csrf},
            headers={"origin": "https://attacker.example"},
        )

    assert missing_csrf.status_code == 403
    assert foreign_origin.status_code == 403


def test_phase3_local_review_and_finalisation_flow(vault_settings, tmp_path: Path) -> None:
    service = SyntheticRouteFinalisationService(tmp_path)
    headshot = tmp_path / "headshot.png"
    headshot.write_bytes(b"synthetic")
    with authenticated_test_app(
        vault_settings, configure_prepared=_configure(service)
    ) as client:
        started = client.post(
            "/phase-2/resume-reviews",
            data={"job_id": "job-1"},
            follow_redirects=False,
        )
        review = client.get("/phase-2/resume-reviews/attempt-1")
        finalised = client.post(
            "/phase-2/resume-reviews/attempt-1/finalise",
            data={
                "confirmation": FINALISE_CONFIRMATION,
                "headshot_path": str(headshot),
            },
            follow_redirects=False,
        )
        artifact_view = client.get("/phase-2/resume-reviews/attempt-1")

    assert started.status_code == 303
    assert started.headers["location"] == "/phase-2/resume-reviews/attempt-1"
    assert review.status_code == 200
    assert "Built Python services." in review.text
    assert FINALISE_CONFIRMATION in review.text
    assert "No final files exist" in review.text
    assert finalised.status_code == 303
    assert finalised.headers["location"] == "/phase-2/resume-reviews/attempt-1"
    assert "Varun_Resume_Acme.docx" in artifact_view.text
    assert "Varun_Resume_Acme.pdf" in artifact_view.text
    assert "upload" not in artifact_view.text.casefold()
    assert "submit application" not in artifact_view.text.casefold()


def test_phase3_route_errors_are_safe_and_route_inventory_is_closed(
    vault_settings, tmp_path: Path
) -> None:
    service = SyntheticRouteFinalisationService(tmp_path)
    with authenticated_test_app(
        vault_settings, configure_prepared=_configure(service)
    ) as client:
        error = client.post("/phase-2/resume-reviews", data={"job_id": "wrong-job"})
        paths = {
            route.path
            for route in phase2_router.routes
            if route.path.startswith("/phase-2/resume-reviews")
        }

    assert error.status_code == 400
    assert "Resume finalisation is unavailable" in error.text
    assert "Synthetic secret detail" not in error.text
    assert paths == {
        "/phase-2/resume-reviews",
        "/phase-2/resume-reviews/{attempt_id}",
        "/phase-2/resume-reviews/{attempt_id}/finalise",
    }
    assert not any(
        word in path
        for path in paths
        for word in (
            "submit",
            "provider",
            "discover",
            "upload",
            "share",
            "drive",
            "schedule",
            "retry",
        )
    )
