from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.permissions import NamedUseService, PermissionService
from job_search_cockpit.facts.review import (
    BulkReviewItem,
    IndividualReviewRequired,
    ReviewService,
    is_resume_eligible,
)
from job_search_cockpit.facts.types import Sensitivity
from job_search_cockpit.imports.service import ImportService
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import (
    Claim,
    ClaimStatus,
    ConfidentialPermissionEvent,
)
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from tests.support.builders import FixedClock


@contextmanager
def _reviewed_vault(
    settings: Settings,
) -> Iterator[tuple[MutationCoordinator, ReviewService, FixedClock]]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    clock = FixedClock()
    importer = ImportService(settings, coordinator, monotonic_clock=clock.monotonic_now)
    importer.apply(importer.preview("session-1", clock.now()).id, "session-1", clock.now())
    try:
        yield coordinator, ReviewService(coordinator), clock
    finally:
        coordinator.dispose()
        lock.release()


def _claim(coordinator: MutationCoordinator, canonical_key: str) -> Claim:
    factory = session_factory_for(coordinator.engine)
    with factory() as session:
        claim = session.scalar(select(Claim).where(Claim.canonical_key == canonical_key))
        assert claim is not None
        session.expunge(claim)
        return claim


def test_conflicting_claim_cannot_be_bulk_approved(vault_settings: Settings) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(coordinator, "profile.product_years")
        assert claim.active_revision_id is not None
        with pytest.raises(IndividualReviewRequired):
            review_service.bulk_approve_low_risk(
                [BulkReviewItem(claim.id, claim.active_revision_id, claim.version)]
            )


def test_conflicting_claim_cannot_bypass_resolution_with_ordinary_correction(
    vault_settings: Settings,
) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(coordinator, "profile.product_years")
        with pytest.raises(IndividualReviewRequired, match="Resolve the source conflict"):
            review_service.correct(
                claim.id,
                {"years": 7},
                "7 years",
                "fixture-employer",
                None,
                None,
                claim.version,
                "Reviewed the discrepancy",
            )


def test_unattributed_global_metric_is_never_resume_eligible(
    vault_settings: Settings,
) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            claim = session.scalar(
                select(Claim).where(Claim.canonical_key.startswith("metric."))
            )
            assert claim is not None
            session.expunge(claim)
        assert claim.active_revision_id is not None
        approved = review_service.approve(claim.id, claim.active_revision_id, claim.version)
        with factory() as session:
            result = is_resume_eligible(
                session,
                approved.id,
                approved.active_revision_id,
                "resume:fixture-1",
            )
        assert result.allowed is False
        assert result.reason == "The fact has no verified employer attribution."


def test_confidential_approved_claim_is_not_eligible_without_exact_permission(
    vault_settings: Settings,
) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(coordinator, "policy.resume.keep-critical-text-parseable-by-ats-software")
        assert claim.active_revision_id is not None
        approved = review_service.approve(claim.id, claim.active_revision_id, claim.version)
        confidential = review_service.set_sensitivity(
            claim.id,
            Sensitivity.CONFIDENTIAL,
            approved.version,
        )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            denied = is_resume_eligible(
                session,
                claim.id,
                confidential.active_revision_id,
                "resume:fixture-1",
            )
        assert denied.allowed is False
        assert denied.reason == "Approved but confidential; explicit permission is required."
        assert confidential.status is ClaimStatus.APPROVED

        named_use = NamedUseService(coordinator).create(
            "resume",
            "fixture-1",
            "Sanitized resume fixture",
            "Varun",
        )
        permission = PermissionService(coordinator).grant(
            claim.id,
            confidential.active_revision_id,
            named_use.id,
            "Varun",
            "GRANT CONFIDENTIAL USE",
            datetime.now(UTC) + timedelta(hours=1),
            expected_event_version=0,
        )
        with factory() as session:
            allowed = is_resume_eligible(
                session,
                claim.id,
                confidential.active_revision_id,
                named_use.id,
                permission.id,
            )
        assert allowed.allowed is True


def test_correction_is_unsupported_until_separately_confirmed(vault_settings: Settings) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(
            coordinator, "policy.resume.report-honest-confidence-and-never-guarantee-an-ats-outcome"
        )
        corrected = review_service.correct(
            claim.id,
            {"text": "Report honest confidence without guarantees."},
            "Report honest confidence without guarantees.",
            None,
            None,
            None,
            claim.version,
            "Clarified wording",
        )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            denied = is_resume_eligible(
                session,
                claim.id,
                corrected.active_revision_id,
                "resume:fixture-1",
            )
        assert denied.allowed is False
        assert "support" in denied.reason.lower()

        supported = review_service.confirm_corrected_support(
            claim.id,
            corrected.active_revision_id,
            corrected.version,
            "Varun",
            "CONFIRM CORRECTED FACT SUPPORT",
            "I confirm this exact wording",
        )
        assert supported.status is ClaimStatus.CORRECTED


def test_expired_permission_is_denied_before_expiry_event_materializes(
    vault_settings: Settings,
) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(
            coordinator, "policy.resume.match-requirements-only-to-truthful-stored-evidence"
        )
        assert claim.active_revision_id is not None
        approved = review_service.approve(claim.id, claim.active_revision_id, claim.version)
        confidential = review_service.set_sensitivity(
            claim.id, Sensitivity.CONFIDENTIAL, approved.version
        )
        named_use = NamedUseService(coordinator).create(
            "resume", "fixture-expired", "Expired fixture", "Varun"
        )
        permission = PermissionService(coordinator).grant(
            claim.id,
            confidential.active_revision_id,
            named_use.id,
            "Varun",
            "GRANT CONFIDENTIAL USE",
            datetime.now(UTC) - timedelta(seconds=1),
            expected_event_version=0,
        )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            result = is_resume_eligible(
                session,
                claim.id,
                confidential.active_revision_id,
                named_use.id,
                permission.id,
            )
        assert result.allowed is False
        assert result.reason == "The confidential-use permission has expired."


def test_due_permission_expiry_is_idempotent(vault_settings: Settings) -> None:
    with _reviewed_vault(vault_settings) as (coordinator, review_service, _clock):
        claim = _claim(
            coordinator, "policy.resume.match-requirements-only-to-truthful-stored-evidence"
        )
        assert claim.active_revision_id is not None
        approved = review_service.approve(claim.id, claim.active_revision_id, claim.version)
        named_use = NamedUseService(coordinator).create(
            "resume", "fixture-due", "Due fixture", "Varun"
        )
        permissions = PermissionService(coordinator)
        grant = permissions.grant(
            claim.id,
            approved.active_revision_id,
            named_use.id,
            "Varun",
            "GRANT CONFIDENTIAL USE",
            datetime.now(UTC) - timedelta(seconds=1),
            expected_event_version=0,
        )

        assert len(permissions.expire_due(datetime.now(UTC))) == 1
        assert permissions.expire_due(datetime.now(UTC)) == ()
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            events = tuple(
                session.scalars(
                    select(ConfidentialPermissionEvent).where(
                        ConfidentialPermissionEvent.permission_id == grant.permission_id
                    )
                )
            )
        assert [event.event_type for event in events] == ["grant", "expire"]
