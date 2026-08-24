from job_search_cockpit.phase1_contract.service import (
    Phase1ContractService,
    Phase1ContractUnavailable,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1ManualContentReviewReceipt,
    Phase1ManualContentReviewRequest,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
)


class InternalPhase1MatchingPort:
    """The only Phase I state handoff available to Phase II."""

    def __init__(self, contract_service: Phase1ContractService) -> None:
        self._contract_service = contract_service

    def activation_inputs(self) -> Phase1ActivationInputs:
        return self._contract_service.snapshot_activation_inputs()

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs:
        current = self.activation_inputs()
        if expected.profile.active_profile_generation != current.profile.active_profile_generation:
            raise Phase1ContractUnavailable("The Phase I profile generation changed.")
        if expected.profile.fingerprint != current.profile.fingerprint:
            raise Phase1ContractUnavailable("The Phase I profile changed.")
        if expected.readiness.readiness_generation != current.readiness.readiness_generation:
            raise Phase1ContractUnavailable("The Phase I readiness generation changed.")
        if (
            expected.readiness.authority_high_water_mark
            != current.readiness.authority_high_water_mark
        ):
            raise Phase1ContractUnavailable("The Phase I authority state changed.")
        if expected.readiness.restore_generation != current.readiness.restore_generation:
            raise Phase1ContractUnavailable("The Phase I restore generation changed.")
        if expected.readiness.import_run_id != current.readiness.import_run_id:
            raise Phase1ContractUnavailable("The Phase I import run changed.")
        if expected.readiness.source_hashes != current.readiness.source_hashes:
            raise Phase1ContractUnavailable("The Phase I source snapshot changed.")
        if expected.readiness.fingerprint != current.readiness.fingerprint:
            raise Phase1ContractUnavailable("The Phase I readiness snapshot changed.")
        if expected.acceptance_receipt.fingerprint != current.acceptance_receipt.fingerprint:
            raise Phase1ContractUnavailable("The Phase I acceptance receipt changed.")
        return current

    def resume_fact_projection(
        self, request: Phase1ResumeFactProjectionRequest
    ) -> Phase1ResumeFactProjection:
        return self._contract_service.snapshot_resume_fact_projection(request)

    def revalidate_resume_fact_projection(
        self, expected: Phase1ResumeFactProjection
    ) -> Phase1ResumeFactProjection:
        return self._contract_service.revalidate_resume_fact_projection(expected)

    def request_manual_content_review(
        self, request: Phase1ManualContentReviewRequest
    ) -> Phase1ManualContentReviewReceipt:
        return self._contract_service.request_manual_content_review(request)
