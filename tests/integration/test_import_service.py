import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from job_search_cockpit.config import Settings
from job_search_cockpit.imports.service import ImportService, PreviewRejected
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import (
    Claim,
    ClaimRevision,
    ClaimStatus,
    ClaimSupportAssertion,
    ImportAttempt,
    ImportRun,
)
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from tests.support.builders import FixedClock


@contextmanager
def _service(settings: Settings) -> Iterator[tuple[ImportService, MutationCoordinator, FixedClock]]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    clock = FixedClock()
    service = ImportService(settings, coordinator, monotonic_clock=clock.monotonic_now)
    try:
        yield service, coordinator, clock
    finally:
        coordinator.dispose()
        lock.release()


def test_identical_import_is_idempotent(vault_settings: Settings) -> None:
    with _service(vault_settings) as (service, _coordinator, clock):
        first_preview = service.preview("session-1", clock.now())
        first = service.apply(first_preview.id, "session-1", clock.now())
        second_preview = service.preview("session-1", clock.now())
        second = service.apply(second_preview.id, "session-1", clock.now())
        assert second.created_claims == 0
        assert second.created_revisions == 0
        assert second.source_statuses == first.source_statuses
        assert second.attempt_id != first.attempt_id


def test_changed_source_creates_revision_without_overwriting_prior_revision(
    vault_settings: Settings,
) -> None:
    with _service(vault_settings) as (service, coordinator, clock):
        first = service.apply(
            service.preview("session-1", clock.now()).id, "session-1", clock.now()
        )
        assert first.created_claims > 0
        factory = session_factory_for(coordinator.engine)
        with factory.begin() as session:
            claim = session.scalar(
                select(Claim).where(Claim.canonical_key == "profile.product_years")
            )
            assert claim is not None
            claim.status = ClaimStatus.APPROVED
            previous_revision_id = claim.active_revision_id

        profile_path = next(
            source.path for source in vault_settings.sources if source.key == "profile_json"
        )
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        payload["pm_years"] = 9
        profile_path.write_text(json.dumps(payload), encoding="utf-8")
        changed = service.apply(
            service.preview("session-1", clock.now()).id,
            "session-1",
            clock.now(),
        )
        assert "profile.product_years" in changed.changed_claims
        with factory() as session:
            claim = session.scalar(
                select(Claim).where(Claim.canonical_key == "profile.product_years")
            )
            assert claim is not None
            assert claim.status is ClaimStatus.UNRESOLVED
            assert claim.active_revision_id != previous_revision_id
            revisions = session.scalars(
                select(ClaimRevision).where(ClaimRevision.claim_id == claim.id)
            ).all()
            assert {revision.display_value for revision in revisions} >= {"8", "9"}


def test_apply_rejects_replayed_or_changed_preview(vault_settings: Settings) -> None:
    with _service(vault_settings) as (service, _coordinator, clock):
        replay = service.preview("session-1", clock.now())
        service.apply(replay.id, "session-1", clock.now())
        with pytest.raises(PreviewRejected, match="already used"):
            service.apply(replay.id, "session-1", clock.now())

        changed = service.preview("session-1", clock.now())
        source_path = next(
            source.path for source in vault_settings.sources if source.key == "profile_json"
        )
        source_path.write_text(source_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with pytest.raises(PreviewRejected, match="changed"):
            service.apply(changed.id, "session-1", clock.now())


def test_preview_expiry_and_session_binding_are_enforced(vault_settings: Settings) -> None:
    with _service(vault_settings) as (service, _coordinator, clock):
        preview = service.preview("session-1", clock.now())
        with pytest.raises(PreviewRejected, match="different session"):
            service.apply(preview.id, "session-2", clock.now())

        expiring = service.preview("session-1", clock.now())
        clock.advance(seconds=600)
        with pytest.raises(PreviewRejected, match="expired"):
            service.apply(expiring.id, "session-1", clock.now())


def test_import_records_runs_attempts_and_documentary_support(vault_settings: Settings) -> None:
    with _service(vault_settings) as (service, coordinator, clock):
        result = service.apply(
            service.preview("session-1", clock.now()).id,
            "session-1",
            datetime.now(UTC),
        )
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(ImportRun)) == 1
            assert session.scalar(select(func.count()).select_from(ImportAttempt)) == 1
            assert (
                session.scalar(select(func.count()).select_from(ClaimSupportAssertion))
                == result.created_revisions
            )


def test_removed_fact_becomes_stale_with_append_only_support_loss(
    vault_settings: Settings,
) -> None:
    with _service(vault_settings) as (service, coordinator, clock):
        service.apply(service.preview("session-1", clock.now()).id, "session-1", clock.now())
        profile_path = next(
            source.path for source in vault_settings.sources if source.key == "profile_json"
        )
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        removed = payload["experience"][1]["bullets"].pop()
        assert "last-mile" in removed
        profile_path.write_text(json.dumps(payload), encoding="utf-8")
        result = service.apply(
            service.preview("session-1", clock.now()).id,
            "session-1",
            clock.now(),
        )
        canonical_key = (
            "employment.example-commerce.led-last-mile-platform-modernization-supporting-annual-gmv"
        )
        assert canonical_key in result.stale_claims
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            claim = session.scalar(select(Claim).where(Claim.canonical_key == canonical_key))
            assert claim is not None and claim.stale is True
            states = session.scalars(
                select(ClaimSupportAssertion.support_state)
                .where(ClaimSupportAssertion.claim_id == claim.id)
                .order_by(ClaimSupportAssertion.created_at)
            ).all()
            assert states == ["supported", "unsupported"]
