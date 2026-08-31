from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.types import Sensitivity
from job_search_cockpit.phase1_contract.matching_port import InternalPhase1MatchingPort
from job_search_cockpit.phase1_contract.service import (
    Phase1BuildMetadata,
    Phase1ContractService,
    Phase1ContractUnavailable,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ManualContentReviewRequest,
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
    Phase1ResumeFactProjectionRequest,
)
from job_search_cockpit.search_profile.catalog import build_profile_v1
from job_search_cockpit.search_profile.service import (
    confirm_profile_change,
    profile_diff_digest,
    seed_profile_v1,
)
from job_search_cockpit.storage.database import create_engine_for, upgrade_database
from job_search_cockpit.storage.models import (
    Claim,
    ClaimRevision,
    ClaimStatus,
    ClaimSupportAssertion,
    ImportRun,
    ImportRunSource,
    Phase1AuthorityState,
)
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator


@contextmanager
def _approved_vault(settings: Settings) -> Iterator[MutationCoordinator]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    try:
        seed_profile_v1(coordinator)
        import_run_id = str(uuid4())

        def add_complete_import(session: object) -> None:
            session.add(
                ImportRun(
                    id=import_run_id,
                    manifest_version="four-source-v1",
                    candidate_digest="a" * 64,
                    status="committed",
                    complete=True,
                )
            )
            for source in settings.sources:
                session.add(
                    ImportRunSource(
                        id=str(uuid4()),
                        import_run_id=import_run_id,
                        source_key=source.key,
                        status="ready",
                        content_hash="b" * 64,
                        failure_class=None,
                        redacted_message=None,
                    )
                )

        coordinator.run(add_complete_import, "sanitized_contract_fixture", expected_version=None)
        yield coordinator
    finally:
        coordinator.dispose()
        lock.release()


def _contract(coordinator: MutationCoordinator) -> Phase1ContractService:
    return Phase1ContractService(
        coordinator,
        Phase1BuildMetadata(
            application_build="test-build",
            acceptance_suite_version="phase1-acceptance-test-v1",
        ),
    )


def _semantic_query(
    *requirements: Phase1MatchingRequirementPredicate,
) -> Phase1MatchingRequirementQuery:
    return Phase1MatchingRequirementQuery(
        requirement_ids=tuple(requirement.requirement_id for requirement in requirements),
        job_revision_id="sanitized-job-revision",
        coverage_ledger_fingerprint="d" * 64,
        launch_session_fingerprint="e" * 64,
        requirements=tuple(requirements),
    )


def _product_delivery_requirement(
    requirement_id: str = "job.required.1",
) -> Phase1MatchingRequirementPredicate:
    return Phase1MatchingRequirementPredicate(
        requirement_id=requirement_id,
        component="responsibility",
        modality="required",
        capability_ids=("capability.product_delivery",),
    )


def _add_fact(
    session: object,
    *,
    suffix: str,
    canonical_key: str,
    wording: str,
    status: ClaimStatus = ClaimStatus.APPROVED,
    sensitivity: Sensitivity = Sensitivity.NORMAL,
    stale: bool = False,
    support_state: str = "supported",
) -> None:
    claim = Claim(
        id=f"claim-{suffix}",
        canonical_key=canonical_key,
        category="skill",
        subject="sanitized-subject",
        status=status,
        sensitivity=sensitivity,
        active_revision_id=None,
        stale=stale,
        version=1,
    )
    session.add(claim)
    revision = ClaimRevision(
        id=f"revision-{suffix}",
        claim_id=claim.id,
        value_json={"private_source_shape": wording},
        display_value=wording,
        semantic_value=f'{{"text":"{suffix}"}}',
        origin="source",
        employer_key="",
        period_start=None,
        period_end=None,
    )
    session.add(revision)
    session.flush()
    claim.active_revision_id = revision.id
    session.add(
        ClaimSupportAssertion(
            id=f"support-{suffix}",
            claim_id=claim.id,
            revision_id=revision.id,
            support_state=support_state,
            support_type="documentary",
            source_evidence_id=None,
            employer_key="",
            period_start=None,
            period_end=None,
            actor="test",
            reason="Sanitized matching fixture",
            supersedes_assertion_id=None,
        )
    )


def test_acceptance_snapshot_binds_exact_verified_state(vault_settings: Settings) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        receipt = contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        inputs = contract.snapshot_activation_inputs()

    assert inputs.acceptance_receipt.id == receipt.id
    assert inputs.readiness.ready_for_phase_2 is True
    assert inputs.profile.version_number == 1
    assert len(inputs.readiness.source_hashes) == 4
    assert inputs.readiness.fingerprint
    assert inputs.profile.fingerprint


def test_missing_phase1_acceptance_fails_closed(vault_settings: Settings) -> None:
    with (
        _approved_vault(vault_settings) as coordinator,
        pytest.raises(Phase1ContractUnavailable, match="acceptance"),
    ):
        _contract(coordinator).snapshot_activation_inputs()


def test_incomplete_latest_import_fails_closed(vault_settings: Settings) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_incomplete_import(session: object) -> None:
            session.add(
                ImportRun(
                    id=str(uuid4()),
                    manifest_version="four-source-v1",
                    candidate_digest="d" * 64,
                    status="incomplete",
                    complete=False,
                )
            )

        coordinator.run(
            add_incomplete_import,
            "sanitized_incomplete_fixture",
            expected_version=None,
        )
        with pytest.raises(Phase1ContractUnavailable, match="not ready"):
            contract.snapshot_activation_inputs()


def test_matching_port_exposes_only_immutable_snapshots(vault_settings: Settings) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        inputs = InternalPhase1MatchingPort(contract).activation_inputs()

    assert not hasattr(inputs, "engine")
    assert "Claim" not in repr(inputs)


def test_matching_port_rejects_a_changed_profile(vault_settings: Settings) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        port = InternalPhase1MatchingPort(contract)
        captured = port.activation_inputs()
        changed = build_profile_v1().model_copy(update={"notice_period_days": 30})
        confirm_profile_change(
            coordinator,
            changed,
            "Sanitized profile change",
            "CREATE NEW SEARCH PROFILE VERSION",
            expected_active_version=1,
            expected_diff_digest=profile_diff_digest(build_profile_v1(), changed),
        )

        with pytest.raises(Phase1ContractUnavailable, match="profile generation"):
            port.revalidate_activation_inputs(captured)


def test_matching_port_projects_only_current_safe_fact_revisions(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_approved_fact(session: object) -> None:
            claim = Claim(
                id="sanitized-claim-1",
                canonical_key="skills.python",
                category="skill",
                subject="sanitized-subject",
                status=ClaimStatus.APPROVED,
                sensitivity=Sensitivity.NORMAL,
                active_revision_id=None,
                stale=False,
                version=1,
            )
            session.add(claim)
            revision = ClaimRevision(
                id="sanitized-revision-1",
                claim_id=claim.id,
                value_json={"text": "Python"},
                display_value="Python",
                semantic_value='{"text":"Python"}',
                origin="source",
                employer_key="",
                period_start=None,
                period_end=None,
            )
            session.add(revision)
            session.flush()
            claim.active_revision_id = revision.id
            session.add(
                ClaimSupportAssertion(
                    id="sanitized-support-1",
                    claim_id=claim.id,
                    revision_id=revision.id,
                    support_state="supported",
                    support_type="documentary",
                    source_evidence_id=None,
                    employer_key="",
                    period_start=None,
                    period_end=None,
                    actor="test",
                    reason="Sanitized contract fixture",
                    supersedes_assertion_id=None,
                )
            )

        coordinator.run(add_approved_fact, "sanitized_resume_projection", expected_version=None)

        projection = InternalPhase1MatchingPort(contract).resume_fact_projection(
            Phase1ResumeFactProjectionRequest(requirement_ids=("skills.python",))
        )

    assert projection.profile_fingerprint
    assert projection.readiness_fingerprint
    assert len(projection.facts) == 1
    assert projection.facts[0].requirement_id == "skills.python"
    assert projection.facts[0].claim_id == "sanitized-claim-1"
    assert projection.facts[0].revision_id == "sanitized-revision-1"
    assert projection.facts[0].safe_wording == "Python"
    assert not hasattr(projection.facts[0], "value_json")


def test_matching_port_returns_opaque_current_fact_set_for_bounded_requirements(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        fact_set = InternalPhase1MatchingPort(contract).matching_fact_set(
            Phase1MatchingRequirementQuery(requirement_ids=("skills.python",))
        )

    assert fact_set.requirement_ids == ("skills.python",)
    assert fact_set.profile_fingerprint
    assert fact_set.fingerprint
    assert not hasattr(fact_set, "safe_wording")


def test_matching_preflight_returns_only_relevant_eligible_wording_hashes(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-semantic-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_matching_facts(session: object) -> None:
            _add_fact(
                session,
                suffix="z-relevant",
                canonical_key="skills.product-delivery-z",
                wording="Led product delivery for a regulated platform.",
            )
            _add_fact(
                session,
                suffix="a-relevant",
                canonical_key="skills.product-delivery-a",
                wording="Owned product delivery across release trains.",
            )
            _add_fact(
                session,
                suffix="unrelated",
                canonical_key="education.example-degree",
                wording="Example postgraduate degree.",
            )

        coordinator.run(add_matching_facts, "semantic_matching_fixture", expected_version=None)
        port = InternalPhase1MatchingPort(contract)
        manifest = port.matching_retrieval_manifest(
            _semantic_query(_product_delivery_requirement())
        )

    assert manifest.complete is True
    assert tuple(choice.canonical_key for choice in manifest.choices) == (
        "skills.product-delivery-a",
        "skills.product-delivery-z",
    )
    assert tuple(choice.claim_id for choice in manifest.choices) == (
        "claim-a-relevant",
        "claim-z-relevant",
    )
    assert all(len(choice.safe_wording_sha256) == 64 for choice in manifest.choices)
    serialized = manifest.model_dump_json()
    assert "Led product delivery" not in serialized
    assert "Owned product delivery" not in serialized
    assert "private_source_shape" not in serialized
    assert "value_json" not in serialized
    assert "engine" not in serialized
    assert "permission" not in serialized
    assert "source_document" not in serialized
    assert "credential" not in serialized


def test_matching_preflight_calls_resume_eligibility_and_excludes_unsafe_facts(
    vault_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-filter-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        accepted_inputs = contract.snapshot_activation_inputs()

        def add_unsafe_facts(session: object) -> None:
            _add_fact(
                session,
                suffix="eligible",
                canonical_key="skills.product-delivery",
                wording="Product delivery ownership.",
            )
            _add_fact(
                session,
                suffix="unapproved",
                canonical_key="skills.product-delivery-unapproved",
                wording="Product delivery unresolved.",
                status=ClaimStatus.UNRESOLVED,
            )
            _add_fact(
                session,
                suffix="stale",
                canonical_key="skills.product-delivery-stale",
                wording="Product delivery stale.",
                stale=True,
            )
            _add_fact(
                session,
                suffix="unsupported",
                canonical_key="skills.product-delivery-unsupported",
                wording="Product delivery unsupported.",
                support_state="unsupported",
            )
            _add_fact(
                session,
                suffix="confidential",
                canonical_key="skills.product-delivery-confidential",
                wording="Product delivery confidential.",
                sensitivity=Sensitivity.CONFIDENTIAL,
            )
            _add_fact(
                session,
                suffix="unreviewed",
                canonical_key="skills.product-delivery-unreviewed",
                wording="Product delivery unreviewed.",
                sensitivity=Sensitivity.UNREVIEWED,
            )

        coordinator.run(add_unsafe_facts, "semantic_filter_fixture", expected_version=None)
        monkeypatch.setattr(contract, "snapshot_activation_inputs", lambda: accepted_inputs)

        manifest = InternalPhase1MatchingPort(contract).matching_retrieval_manifest(
            _semantic_query(_product_delivery_requirement())
        )

    assert tuple(choice.claim_id for choice in manifest.choices) == ("claim-eligible",)
    assert manifest.candidate_universe_count == 1
    assert manifest.examined_count == 1
    assert dict(manifest.omission_reason_counts)["ineligible_fact"] == 5


def test_matching_preflight_cap_and_authority_drift_fail_closed(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-cap-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_many_facts(session: object) -> None:
            for index in range(33):
                _add_fact(
                    session,
                    suffix=f"cap-{index:02d}",
                    canonical_key=f"skills.product-delivery-{index:02d}",
                    wording=f"Product delivery responsibility {index}.",
                )

        coordinator.run(add_many_facts, "semantic_cap_fixture", expected_version=None)
        port = InternalPhase1MatchingPort(contract)
        manifest = port.matching_retrieval_manifest(
            _semantic_query(_product_delivery_requirement())
        )

        assert manifest.complete is False
        assert len(manifest.choices) == 32
        assert dict(manifest.omission_reason_counts)["relevant_choice_cap_exceeded"] == 1

        def change_authority(session: object) -> None:
            authority = session.get(Phase1AuthorityState, 1)
            assert authority is not None
            authority.readiness_generation += 1

        coordinator.run(change_authority, "semantic_authority_drift", expected_version=None)

        with pytest.raises(Phase1ContractUnavailable, match="retrieval manifest changed"):
            port.revalidate_matching_retrieval_manifest(manifest)


def test_matching_port_rejects_a_changed_resume_fact_projection(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        port = InternalPhase1MatchingPort(contract)
        projection = port.resume_fact_projection(
            Phase1ResumeFactProjectionRequest(
                requirement_ids=("skills.python",)
            )
        )

        def change_readiness_generation(session: object) -> None:
            authority = session.get(Phase1AuthorityState, 1)
            assert authority is not None
            authority.readiness_generation += 1

        coordinator.run(
            change_readiness_generation,
            "sanitized_projection_change",
            expected_version=None,
        )

        with pytest.raises(Phase1ContractUnavailable, match="fact projection changed"):
            port.revalidate_resume_fact_projection(projection)


def test_matching_port_sends_manual_content_to_phase1_review(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-118-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        receipt = InternalPhase1MatchingPort(contract).request_manual_content_review(
            Phase1ManualContentReviewRequest(
                canonical_key="application.answer.work_authorization",
                category="application_answer",
                safe_wording="Authorized to work in the stated location.",
            )
        )

    assert receipt.status == "unresolved"
    assert receipt.origin == "user"
