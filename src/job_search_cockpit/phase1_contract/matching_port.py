from job_search_cockpit.phase1_contract.service import (
    Phase1ContractService,
    Phase1ContractUnavailable,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    Phase1DisclosureAuthorizationRequest,
    Phase1DisclosureEpochRequest,
    Phase1DisclosureEpochSnapshot,
    Phase1DisclosureLifecycleRequest,
    Phase1DisclosureLifecycleSnapshot,
    Phase1FactDisclosureAuthorizationSnapshot,
    Phase1ManualContentReviewReceipt,
    Phase1ManualContentReviewRequest,
    Phase1MatchingFactSetSnapshot,
    Phase1MatchingRequirementQuery,
    Phase1MatchingRetrievalManifest,
    Phase1MatchingWordingRelease,
    Phase1ResumeFactProjection,
    Phase1ResumeFactProjectionRequest,
    Phase1WordingReleaseRequest,
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

    def matching_fact_set(
        self, query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingFactSetSnapshot:
        return self._contract_service.snapshot_matching_fact_set(query)

    def revalidate_matching_fact_set(
        self, expected: Phase1MatchingFactSetSnapshot
    ) -> Phase1MatchingFactSetSnapshot:
        return self._contract_service.revalidate_matching_fact_set(expected)

    def matching_retrieval_manifest(
        self, query: Phase1MatchingRequirementQuery
    ) -> Phase1MatchingRetrievalManifest:
        return self._contract_service.snapshot_matching_retrieval_manifest(query)

    def revalidate_matching_retrieval_manifest(
        self, expected: Phase1MatchingRetrievalManifest
    ) -> Phase1MatchingRetrievalManifest:
        return self._contract_service.revalidate_matching_retrieval_manifest(expected)

    def authorize_matching_disclosure(
        self, request: Phase1DisclosureAuthorizationRequest
    ) -> Phase1FactDisclosureAuthorizationSnapshot:
        return self._contract_service.authorize_matching_disclosure(request)

    def release_matching_wording(
        self, request: Phase1WordingReleaseRequest
    ) -> Phase1MatchingWordingRelease:
        return self._contract_service.release_matching_wording(request)

    def record_disclosure_lifecycle(
        self, request: Phase1DisclosureLifecycleRequest
    ) -> Phase1DisclosureLifecycleSnapshot:
        return self._contract_service.record_disclosure_lifecycle(request)

    def start_new_matching_disclosure_epoch(
        self, request: Phase1DisclosureEpochRequest
    ) -> Phase1DisclosureEpochSnapshot:
        return self._contract_service.start_new_matching_disclosure_epoch(request)

    def request_manual_content_review(
        self, request: Phase1ManualContentReviewRequest
    ) -> Phase1ManualContentReviewReceipt:
        return self._contract_service.request_manual_content_review(request)
