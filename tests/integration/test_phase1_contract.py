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
