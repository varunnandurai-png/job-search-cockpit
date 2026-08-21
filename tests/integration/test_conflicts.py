import json
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.conflicts import (
    ResolveConflictCommand,
    resolve_conflict,
)
from job_search_cockpit.imports.service import ImportService
from job_search_cockpit.storage.database import (
    create_engine_for,
    session_factory_for,
    upgrade_database,
)
from job_search_cockpit.storage.models import ConflictGroup, ConflictMember, ConflictResolution
from job_search_cockpit.storage.mutation import AppInstanceLock, MutationCoordinator
from tests.support.builders import FixedClock


@contextmanager
def _imported_vault(
    settings: Settings,
) -> Iterator[tuple[MutationCoordinator, ImportService, FixedClock]]:
    upgrade_database(f"sqlite:///{settings.database_path}")
    engine = create_engine_for(settings)
    lock = AppInstanceLock.acquire(settings)
    coordinator = MutationCoordinator(settings, engine, lock)
    clock = FixedClock()
    service = ImportService(settings, coordinator, monotonic_clock=clock.monotonic_now)
    try:
        service.apply(service.preview("session-1", clock.now()).id, "session-1", clock.now())
        yield coordinator, service, clock
    finally:
        coordinator.dispose()
        lock.release()


def test_import_surfaces_product_year_and_team_scope_conflicts(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, _service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            groups = session.scalars(
                select(ConflictGroup).where(ConflictGroup.status == "open")
            ).all()
            families = {group.semantic_family for group in groups}
            assert "profile.product_years" in families
            assert "team_scope.jpmorganchase" in families


def test_import_does_not_group_unrelated_numeric_facts_as_a_conflict(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, _service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            families = set(
                session.scalars(
                    select(ConflictGroup.semantic_family).where(ConflictGroup.status == "open")
                )
            )
            assert "metric.statement" not in families


def test_import_does_not_treat_punctuation_only_education_variants_as_a_conflict(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, _service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            families = set(
                session.scalars(
                    select(ConflictGroup.semantic_family).where(ConflictGroup.status == "open")
                )
            )
            assert not any("example-school-mba" in family for family in families)


def test_import_does_not_conflate_an_unnumbered_team_statement_with_team_counts(
    vault_settings: Settings,
) -> None:
    profile = next(source.path for source in vault_settings.sources if source.key == "profile_json")
    payload = json.loads(profile.read_text(encoding="utf-8"))
    payload["experience"][0]["bullets"].append("Partnered with Scrum teams on launch planning.")
    profile.write_text(json.dumps(payload), encoding="utf-8")

    with _imported_vault(vault_settings) as (coordinator, _service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            group = session.scalar(
                select(ConflictGroup).where(
                    ConflictGroup.semantic_family == "team_scope.jpmorganchase",
                    ConflictGroup.status == "open",
                )
            )
            assert group is not None
            members = session.scalars(
                select(ConflictMember).where(ConflictMember.conflict_group_id == group.id)
            ).all()
            assert len(members) == 2


def test_preview_reports_conflicts_without_selecting_a_winner(vault_settings: Settings) -> None:
    upgrade_database(f"sqlite:///{vault_settings.database_path}")
    engine = create_engine_for(vault_settings)
    lock = AppInstanceLock.acquire(vault_settings)
    coordinator = MutationCoordinator(vault_settings, engine, lock)
    clock = FixedClock()
    try:
        service = ImportService(vault_settings, coordinator, monotonic_clock=clock.monotonic_now)
        preview = service.preview("session-1", clock.now())
        assert preview.conflict_count >= 2
    finally:
        coordinator.dispose()
        lock.release()


def test_conflict_resolution_requires_explicit_versioned_selection(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, _service, _clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            group = session.scalar(
                select(ConflictGroup).where(
                    ConflictGroup.semantic_family == "profile.product_years",
                    ConflictGroup.status == "open",
                )
            )
            assert group is not None
            member = session.scalar(
                select(ConflictMember).where(ConflictMember.conflict_group_id == group.id)
            )
            assert member is not None
            group_id = group.id
            revision_id = member.revision_id
            expected_version = group.version
        resolved = resolve_conflict(
            coordinator,
            ResolveConflictCommand(
                group_id=group_id,
                selected_revision_id=revision_id,
                corrected_value=None,
                corrected_display_value=None,
                expected_group_version=expected_version,
                reason="Selected the source-backed direct-product duration",
                employer_key=None,
                period_start=None,
                period_end=None,
            ),
        )
        assert resolved.status == "resolved"
        with factory() as session:
            resolution = session.scalar(
                select(ConflictResolution).where(ConflictResolution.conflict_group_id == group_id)
            )
            assert resolution is not None
            assert resolution.selected_revision_id == revision_id


def test_identical_reimport_does_not_reopen_resolved_conflict(vault_settings: Settings) -> None:
    with _imported_vault(vault_settings) as (coordinator, service, clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            group = session.scalar(
                select(ConflictGroup).where(
                    ConflictGroup.semantic_family == "profile.product_years",
                    ConflictGroup.status == "open",
                )
            )
            assert group is not None
            member = session.scalar(
                select(ConflictMember).where(ConflictMember.conflict_group_id == group.id)
            )
            assert member is not None
            command = ResolveConflictCommand(
                group_id=group.id,
                selected_revision_id=member.revision_id,
                corrected_value=None,
                corrected_display_value=None,
                expected_group_version=group.version,
                reason="Selected the source-backed direct-product duration",
                employer_key=None,
                period_start=None,
                period_end=None,
            )
        resolved = resolve_conflict(coordinator, command)
        service.apply(service.preview("session-1", clock.now()).id, "session-1", clock.now())
        with factory() as session:
            group = session.get(ConflictGroup, resolved.group_id)
            assert group is not None
            assert group.status == "resolved"
            assert group.version == resolved.version


def test_open_conflict_closes_when_current_source_disagreement_disappears(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, service, clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            group = session.scalar(
                select(ConflictGroup).where(
                    ConflictGroup.semantic_family == "profile.product_years",
                    ConflictGroup.status == "open",
                )
            )
            assert group is not None
            group_id = group.id
        assessment = next(
            source.path for source in vault_settings.sources if source.key == "assessment"
        )
        assessment.write_text(
            "# Assessment\n\nRecommended search allocation remains unchanged.\n",
            encoding="utf-8",
        )
        service.apply(service.preview("session-1", clock.now()).id, "session-1", clock.now())

        with factory() as session:
            group = session.get(ConflictGroup, group_id)
            assert group is not None and group.status == "resolved"
            closure = session.scalar(
                select(ConflictResolution).where(
                    ConflictResolution.conflict_group_id == group_id,
                    ConflictResolution.resolution_type == "closed",
                )
            )
            assert closure is not None


def test_incomplete_import_cannot_close_a_conflict_from_an_unavailable_source(
    vault_settings: Settings,
) -> None:
    with _imported_vault(vault_settings) as (coordinator, service, clock):
        factory = session_factory_for(coordinator.engine)
        with factory() as session:
            group = session.scalar(
                select(ConflictGroup).where(
                    ConflictGroup.semantic_family == "profile.product_years",
                    ConflictGroup.status == "open",
                )
            )
            assert group is not None
            group_id = group.id
        profile = next(
            source.path for source in vault_settings.sources if source.key == "profile_json"
        )
        original = profile.read_text(encoding="utf-8")
        profile.unlink()
        incomplete = service.preview("session-1", clock.now())
        service.apply(
            incomplete.id,
            "session-1",
            clock.now(),
            confirm_incomplete=True,
        )
        profile.write_text(original, encoding="utf-8")
        service.apply(service.preview("session-1", clock.now()).id, "session-1", clock.now())

        with factory() as session:
            group = session.get(ConflictGroup, group_id)
            assert group is not None and group.status == "open"
