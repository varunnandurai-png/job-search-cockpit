from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

import job_search_cockpit.phase1_contract.service as phase1_service_module
from job_search_cockpit.config import Settings
from job_search_cockpit.facts.types import Sensitivity
from job_search_cockpit.phase1_contract.matching_port import InternalPhase1MatchingPort
from job_search_cockpit.phase1_contract.service import (
    Phase1BuildMetadata,
    Phase1ContractService,
    Phase1ContractUnavailable,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1DisclosureAuthorizationRequest,
    Phase1DisclosureEpochRequest,
    Phase1DisclosureLifecycleRequest,
    Phase1DisclosurePayloadContext,
    Phase1ManualContentReviewRequest,
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
    Phase1ResumeFactProjectionRequest,
    Phase1WordingReleaseRequest,
    canonical_fingerprint,
)
from job_search_cockpit.search_profile.catalog import build_profile_v1
from job_search_cockpit.search_profile.service import (
    confirm_profile_change,
    profile_diff_digest,
    seed_profile_v1,
)
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import (
    AuditEvent,
    Claim,
    ClaimRevision,
    ClaimStatus,
    ClaimSupportAssertion,
    ImportRun,
    ImportRunSource,
    Phase1AcceptanceReceipt,
    Phase1AuthorityState,
    Phase1FactDisclosureAuthorization,
    Phase1FactDisclosureLifecycleEvent,
    Phase1FactDisclosureReleaseEvent,
    Phase1MatchingDisclosureEpoch,
    Phase1MatchingRetrievalPreflight,
)
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from job_search_cockpit.storage.recovery_ledger import RecoveryEvent


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
    assert "skills.product-delivery" not in serialized


def _disclosure_request(
    manifest: object,
    *,
    attempt_id: str = "attempt-1",
    nonce: str = "nonce-1",
    expires_at: datetime | None = None,
) -> Phase1DisclosureAuthorizationRequest:
    now = datetime.now(UTC)
    issued_at = expires_at - timedelta(minutes=10) if expires_at is not None else now
    context = Phase1DisclosurePayloadContext(
        packet_id="packet-1",
        attempt_id=attempt_id,
        nonce=nonce,
        manifest_fingerprint=manifest.fingerprint,
        job_revision_id=manifest.query.job_revision_id,
        selected_location_path=("India", "Telangana", "Hyderabad"),
        coverage_ledger_fingerprint=manifest.query.coverage_ledger_fingerprint,
        validated_requirements_fingerprint="1" * 64,
        rubric_fingerprint="2" * 64,
        retrieval_configuration_version=manifest.retrieval_policy_version,
        interpreter_configuration_version="local-manual.v1",
        response_schema_version="mapping-response.v1",
        phase1_profile_generation=manifest.profile_generation,
        phase1_readiness_generation=manifest.readiness_generation,
        phase1_authority_generation=manifest.authority_generation,
        phase1_restore_generation=manifest.restore_generation,
        disclosure_budget_epoch=manifest.disclosure_budget_epoch,
        disclosure_policy_generation=manifest.disclosure_policy_generation,
        phase2_activation_generation=7,
        phase2_restore_generation=3,
        recipient_mode="local_manual",
        issued_at=issued_at,
        expires_at=expires_at or now + timedelta(minutes=10),
        phase2_authorization_id="phase2-auth-1",
        allowed_relations=("direct", "adjacent", "none"),
        allowed_reason_codes=("approved_evidence", "no_approved_evidence"),
    )
    digest = Phase1ContractService.disclosure_payload_digest(manifest, context)
    return Phase1DisclosureAuthorizationRequest(context=context, logical_payload_digest=digest)


def _ready_manifest(
    coordinator: MutationCoordinator, contract: Phase1ContractService, *, suffix: str = "one"
) -> object:
    def add_fact(session: object) -> None:
        _add_fact(
            session,
            suffix=suffix,
            canonical_key=f"skills.product-delivery-{suffix}",
            wording=f"Approved safe wording {suffix}.",
        )

    coordinator.run(add_fact, f"disclosure_fixture_{suffix}", expected_version=None)
    return contract.snapshot_matching_retrieval_manifest(
        _semantic_query(_product_delivery_requirement())
    )


def test_preflight_is_durable_reused_and_changed_scope_is_rejected(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-preflight-durable",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        manifest = _ready_manifest(coordinator, contract)
        repeated = contract.snapshot_matching_retrieval_manifest(manifest.query)
        changed = manifest.query.model_copy(update={"launch_session_fingerprint": "f" * 64})

        assert repeated == manifest
        with pytest.raises(Phase1ContractUnavailable, match="preflight scope"):
            contract.snapshot_matching_retrieval_manifest(changed)
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            assert len(tuple(session.scalars(select(Phase1MatchingRetrievalPreflight)))) == 1


def test_disclosure_requires_exact_digest_releases_hash_verified_wording_and_blocks_replay(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-disclosure-pass",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        manifest = _ready_manifest(coordinator, contract)
        request = _disclosure_request(manifest)

        with pytest.raises(Phase1ContractUnavailable, match="digest"):
            contract.authorize_matching_disclosure(
                _disclosure_request(
                    manifest, attempt_id="attempt-bad-digest", nonce="nonce-bad"
                ).model_copy(update={"logical_payload_digest": "0" * 64})
            )
        receipt = contract.authorize_matching_disclosure(request)
        assert contract.authorize_matching_disclosure(request) == receipt
        changed_context = request.context.model_copy(update={"nonce": "changed-nonce"})
        changed_request = Phase1DisclosureAuthorizationRequest(
            context=changed_context,
            logical_payload_digest=contract.disclosure_payload_digest(manifest, changed_context),
        )
        with pytest.raises(Phase1ContractUnavailable, match="cannot be reused"):
            contract.authorize_matching_disclosure(changed_request)
        with pytest.raises(Phase1ContractUnavailable, match="terminal or invalid"):
            contract.record_disclosure_lifecycle(
                Phase1DisclosureLifecycleRequest(
                    authorization_id=receipt.authorization_id,
                    logical_payload_digest=receipt.logical_payload_digest,
                    state="validated_response",
                )
            )
        release_request = Phase1WordingReleaseRequest(
            authorization=receipt,
            attempt_id=request.context.attempt_id,
            nonce=request.context.nonce,
        )
        first = contract.release_matching_wording(release_request)
        rerelease = contract.release_matching_wording(release_request)
        assert first == rerelease
        assert first.choices[0].canonical_key == "skills.product-delivery-one"
        assert first.choices[0].safe_wording == "Approved safe wording one."
        assert first.choices[0].safe_wording_sha256 == manifest.choices[0].safe_wording_sha256

        contract.record_disclosure_lifecycle(
            Phase1DisclosureLifecycleRequest(
                authorization_id=receipt.authorization_id,
                logical_payload_digest=receipt.logical_payload_digest,
                state="consuming",
            )
        )
        with pytest.raises(Phase1ContractUnavailable, match="replayed"):
            contract.release_matching_wording(release_request)
        with pytest.raises(Phase1ContractUnavailable, match="replayed"):
            contract.authorize_matching_disclosure(request)
        failed = contract.record_disclosure_lifecycle(
            Phase1DisclosureLifecycleRequest(
                authorization_id=receipt.authorization_id,
                logical_payload_digest=receipt.logical_payload_digest,
                state="failed",
                reason_code="publication_failed",
            )
        )
        assert (
            contract.record_disclosure_lifecycle(
                Phase1DisclosureLifecycleRequest(
                    authorization_id=receipt.authorization_id,
                    logical_payload_digest=receipt.logical_payload_digest,
                    state="failed",
                    reason_code="retry_after_phase2_recovery",
                )
            )
            == failed
        )

        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            authorization = session.get(Phase1FactDisclosureAuthorization, receipt.authorization_id)
            assert authorization is not None
            assert "Approved safe wording" not in str(authorization.context_json)
            assert request.context.nonce not in str(authorization.context_json)
            assert (
                len(
                    tuple(
                        session.scalars(
                            select(Phase1FactDisclosureLifecycleEvent).where(
                                Phase1FactDisclosureLifecycleEvent.authorization_id
                                == receipt.authorization_id
                            )
                        )
                    )
                )
                == 3
            )
            assert (
                len(
                    tuple(
                        session.scalars(
                            select(Phase1FactDisclosureReleaseEvent).where(
                                Phase1FactDisclosureReleaseEvent.authorization_id
                                == receipt.authorization_id
                            )
                        )
                    )
                )
                == 2
            )
            audit_events = tuple(
                session.scalars(select(AuditEvent).where(AuditEvent.area == "matching_disclosure"))
            )
            assert len(audit_events) >= 2


def test_expiry_discovered_at_release_is_recorded_and_never_released(
    vault_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-disclosure-expired",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        manifest = _ready_manifest(coordinator, contract)
        request = _disclosure_request(manifest)
        receipt = contract.authorize_matching_disclosure(request)
        assert receipt.state == "authorized"

        class AfterExpiry(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:
                del tz
                return request.context.expires_at + timedelta(seconds=1)

        monkeypatch.setattr(phase1_service_module, "datetime", AfterExpiry)
        with pytest.raises(Phase1ContractUnavailable, match="expired"):
            contract.release_matching_wording(
                Phase1WordingReleaseRequest(
                    authorization=receipt,
                    attempt_id=request.context.attempt_id,
                    nonce=request.context.nonce,
                )
            )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            states = tuple(
                session.scalars(
                    select(Phase1FactDisclosureLifecycleEvent.state)
                    .where(
                        Phase1FactDisclosureLifecycleEvent.authorization_id
                        == receipt.authorization_id
                    )
                    .order_by(Phase1FactDisclosureLifecycleEvent.sequence)
                )
            )
            assert states == ("authorized", "expired")


def test_expiry_before_lifecycle_is_returned_as_a_durable_terminal_receipt(
    vault_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-disclosure-lifecycle-expired",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        manifest = _ready_manifest(coordinator, contract)
        request = _disclosure_request(manifest)
        receipt = contract.authorize_matching_disclosure(request)

        class AfterExpiry(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:
                del tz
                return request.context.expires_at + timedelta(seconds=1)

        monkeypatch.setattr(phase1_service_module, "datetime", AfterExpiry)
        lifecycle = contract.record_disclosure_lifecycle(
            Phase1DisclosureLifecycleRequest(
                authorization_id=receipt.authorization_id,
                logical_payload_digest=receipt.logical_payload_digest,
                state="consuming",
            )
        )
        assert lifecycle.state == "expired"

        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            states = tuple(
                session.scalars(
                    select(Phase1FactDisclosureLifecycleEvent.state)
                    .where(
                        Phase1FactDisclosureLifecycleEvent.authorization_id
                        == receipt.authorization_id
                    )
                    .order_by(Phase1FactDisclosureLifecycleEvent.sequence)
                )
            )
            assert states == ("authorized", "expired")


def test_disclosure_epoch_requires_exact_confirmation_and_is_monotonic(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        with pytest.raises(Phase1ContractUnavailable, match="confirmation"):
            contract.start_new_matching_disclosure_epoch(
                Phase1DisclosureEpochRequest(reason="Budget exhausted", confirmation="wrong")
            )
        first = contract.start_new_matching_disclosure_epoch(
            Phase1DisclosureEpochRequest(
                reason="Budget exhausted after reviewed attempts",
                confirmation="START NEW MATCHING DISCLOSURE EPOCH",
            )
        )
        second = contract.start_new_matching_disclosure_epoch(
            Phase1DisclosureEpochRequest(
                reason="A separately reviewed matching campaign",
                confirmation="START NEW MATCHING DISCLOSURE EPOCH",
            )
        )
        assert (first.epoch_number, second.epoch_number) == (2, 3)
        assert (first.policy_generation, second.policy_generation) == (2, 3)
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            epochs = tuple(
                session.scalars(
                    select(Phase1MatchingDisclosureEpoch).order_by(
                        Phase1MatchingDisclosureEpoch.epoch_number
                    )
                )
            )
            assert [epoch.epoch_number for epoch in epochs] == [1, 2, 3]


def test_activation_rejects_an_acceptance_receipt_from_an_older_schema(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-current-schema",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_outdated_receipt(session: object) -> None:
            payload = {
                "application_build": "older-build",
                "schema_revision": "0002_phase1_contract",
                "acceptance_suite_version": "older-suite",
                "acceptance_run_id": "run-older-schema",
                "result": "passed",
                "result_fingerprint": "d" * 64,
                "restore_high_water_mark": 0,
                "actor": "Varun",
                "confirmation": "I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
            }
            session.add(
                Phase1AcceptanceReceipt(
                    id="outdated-schema-receipt",
                    **payload,
                    fingerprint=canonical_fingerprint(payload),
                )
            )

        coordinator.run(add_outdated_receipt, "outdated_acceptance_fixture", expected_version=None)

        with pytest.raises(Phase1ContractUnavailable, match="current acceptance receipt"):
            contract.snapshot_activation_inputs()


def _taxonomy_requirement(index: int, taxonomy_id: str) -> Phase1MatchingRequirementPredicate:
    field_by_prefix = {
        "capability": "capability_ids",
        "responsibility": "responsibility_ids",
        "domain": "domain_ids",
    }
    prefix = taxonomy_id.split(".", 1)[0]
    return Phase1MatchingRequirementPredicate(
        requirement_id=f"job.taxonomy.{index:02d}",
        component="evidence",
        modality="preferred",
        **{field_by_prefix[prefix]: (taxonomy_id,)},
    )


def _taxonomy_query(
    job_suffix: str, taxonomy_ids: tuple[str, ...]
) -> Phase1MatchingRequirementQuery:
    requirements = tuple(
        _taxonomy_requirement(index, taxonomy_id)
        for index, taxonomy_id in enumerate(taxonomy_ids, start=1)
    )
    return Phase1MatchingRequirementQuery(
        requirement_ids=tuple(item.requirement_id for item in requirements),
        job_revision_id=f"job-revision-{job_suffix}",
        coverage_ledger_fingerprint=canonical_fingerprint({"coverage": job_suffix}),
        launch_session_fingerprint=canonical_fingerprint({"launch": job_suffix}),
        requirements=requirements,
    )


def test_taxonomy_budget_denies_the_33rd_unique_id_and_new_epoch_resets_active_budget(
    vault_settings: Settings,
) -> None:
    taxonomy_ids = (
        "capability.applied_ai",
        "capability.cross_functional_leadership",
        "capability.data_analytics",
        "capability.lifecycle_management",
        "capability.partner_integration",
        "capability.platform_product",
        "capability.product_delivery",
        "capability.product_discovery",
        "capability.product_strategy",
        "capability.roadmap_prioritization",
        "capability.stakeholder_influence",
        "responsibility.delivery_ownership",
        "responsibility.discovery_ownership",
        "responsibility.executive_influence",
        "responsibility.kpi_ownership",
        "responsibility.people_leadership",
        "responsibility.product_decisions",
        "responsibility.roadmap_ownership",
        "responsibility.technical_tradeoffs",
        "domain.applied_ai",
        "domain.banking",
        "domain.billing",
        "domain.commerce",
        "domain.decision_support",
        "domain.ecommerce",
        "domain.fintech",
        "domain.fraud",
        "domain.fulfilment",
        "domain.home_buying",
        "domain.last_mile",
        "domain.lending",
        "domain.mortgage",
        "domain.omnichannel",
    )
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-taxonomy-budget",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )

        def add_known_fact(session: object) -> None:
            _add_fact(
                session,
                suffix="budget-known",
                canonical_key="skills.product-delivery-budget-known",
                wording="Approved product delivery wording.",
            )

        coordinator.run(add_known_fact, "taxonomy_budget_fixture", expected_version=None)
        first_manifest = contract.snapshot_matching_retrieval_manifest(
            _taxonomy_query("first", taxonomy_ids[:24])
        )
        second_manifest = contract.snapshot_matching_retrieval_manifest(
            _taxonomy_query("second", taxonomy_ids[24:32])
        )
        third_manifest = contract.snapshot_matching_retrieval_manifest(
            _taxonomy_query("third", taxonomy_ids[32:])
        )
        contract.authorize_matching_disclosure(
            _disclosure_request(first_manifest, attempt_id="budget-1", nonce="budget-nonce-1")
        )
        contract.authorize_matching_disclosure(
            _disclosure_request(second_manifest, attempt_id="budget-2", nonce="budget-nonce-2")
        )
        with pytest.raises(Phase1ContractUnavailable, match="taxonomy_budget_exhausted"):
            contract.authorize_matching_disclosure(
                _disclosure_request(third_manifest, attempt_id="budget-3", nonce="budget-nonce-3")
            )

        contract.start_new_matching_disclosure_epoch(
            Phase1DisclosureEpochRequest(
                reason="Reviewed taxonomy budget renewal",
                confirmation="START NEW MATCHING DISCLOSURE EPOCH",
            )
        )
        renewed_manifest = contract.snapshot_matching_retrieval_manifest(
            _taxonomy_query("third", taxonomy_ids[32:])
        )
        renewed = contract.authorize_matching_disclosure(
            _disclosure_request(renewed_manifest, attempt_id="budget-4", nonce="budget-nonce-4")
        )
        assert renewed.disclosure_budget_epoch == 2

        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            authorizations = tuple(session.scalars(select(Phase1FactDisclosureAuthorization)))
            assert len(authorizations) == 4
            assert {row.disclosure_budget_epoch for row in authorizations} == {1, 2}


def test_recovery_only_authorization_still_charges_the_fact_budget(
    vault_settings: Settings,
) -> None:
    with _approved_vault(vault_settings) as coordinator:
        contract = _contract(coordinator)
        contract.record_acceptance(
            acceptance_run_id="run-recovery-budget",
            result_fingerprint="c" * 64,
            actor="Varun",
            confirmation="I ACCEPT THE PHASE I ACCEPTANCE RECEIPT",
        )
        manifest = _ready_manifest(coordinator, contract)
        coordinator.recovery_ledger.append(
            RecoveryEvent(
                event_id="recovery-only-disclosure",
                event_type="matching_disclosure_authorization",
                payload={
                    "attempt_id": "recovered-attempt",
                    "epoch": 1,
                    "fact_ids": [f"recovered-claim-{index:02d}" for index in range(64)],
                    "taxonomy_ids": [],
                },
                created_at=datetime.now(UTC),
            )
        )

        with pytest.raises(Phase1ContractUnavailable, match="fact_budget_exhausted"):
            contract.authorize_matching_disclosure(
                _disclosure_request(
                    manifest,
                    attempt_id="post-recovery-attempt",
                    nonce="post-recovery-nonce",
                )
            )


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
            Phase1ResumeFactProjectionRequest(requirement_ids=("skills.python",))
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
