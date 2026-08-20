from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from job_search_cockpit.config import Settings
from job_search_cockpit.facts.types import Sensitivity
from job_search_cockpit.storage.database import session_factory_for
from job_search_cockpit.storage.models import (
    Claim,
    ClaimStatus,
    ClaimSupportAssertion,
    ConflictGroup,
    ImportRun,
    ImportRunSource,
    SearchProfileVersion,
)
from job_search_cockpit.storage.mutation import MutationCoordinator


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready_for_phase_2: bool
    unresolved: int
    sensitivity_unreviewed: int
    stale: int
    open_conflicts: int
    unsupported_approved: int
    latest_import_complete: bool
    active_profile_version: int | None
    next_action: str


class ReadinessService:
    def __init__(self, coordinator: MutationCoordinator) -> None:
        self.coordinator = coordinator

    @staticmethod
    def _count(session: Session, statement: Select[tuple[int]]) -> int:
        value = session.scalar(statement)
        return int(value or 0)

    def report(self) -> ReadinessReport:
        factory = session_factory_for(self.coordinator.engine)
        with factory() as session:
            unresolved = self._count(
                session,
                select(func.count())
                .select_from(Claim)
                .where(Claim.status == ClaimStatus.UNRESOLVED),
            )
            sensitivity_unreviewed = self._count(
                session,
                select(func.count())
                .select_from(Claim)
                .where(Claim.sensitivity == Sensitivity.UNREVIEWED),
            )
            stale = self._count(
                session, select(func.count()).select_from(Claim).where(Claim.stale.is_(True))
            )
            open_conflicts = self._count(
                session,
                select(func.count())
                .select_from(ConflictGroup)
                .where(ConflictGroup.status == "open"),
            )
            approved_claims = tuple(
                session.scalars(
                    select(Claim).where(
                        Claim.status.in_((ClaimStatus.APPROVED, ClaimStatus.CORRECTED))
                    )
                )
            )
            unsupported_approved = 0
            for claim in approved_claims:
                support = session.scalar(
                    select(ClaimSupportAssertion)
                    .where(
                        ClaimSupportAssertion.claim_id == claim.id,
                        ClaimSupportAssertion.revision_id == claim.active_revision_id,
                    )
                    .order_by(ClaimSupportAssertion.created_at.desc())
                )
                if support is None or support.support_state != "supported":
                    unsupported_approved += 1

            latest = session.scalar(
                select(ImportRun)
                .where(ImportRun.status == "committed")
                .order_by(ImportRun.committed_at.desc(), ImportRun.id.desc())
            )
            latest_import_complete = False
            if latest is not None and latest.complete:
                statuses: dict[str, str] = {
                    source_key: status
                    for source_key, status in session.execute(
                        select(ImportRunSource.source_key, ImportRunSource.status).where(
                            ImportRunSource.import_run_id == latest.id
                        )
                    ).all()
                }
                latest_import_complete = set(statuses) == {
                    source.key for source in Settings().sources
                } and all(status == "ready" for status in statuses.values())
            active_profile = session.scalar(
                select(SearchProfileVersion).where(SearchProfileVersion.active.is_(True))
            )
            profile_version = active_profile.version_number if active_profile else None

        blockers = (
            (not latest_import_complete, "Import all four curated sources."),
            (profile_version is None, "Create the locked target search profile."),
            (open_conflicts > 0, "Resolve open source conflicts."),
            (unresolved > 0, "Review unresolved facts."),
            (sensitivity_unreviewed > 0, "Review fact confidentiality."),
            (stale > 0, "Review stale facts."),
            (unsupported_approved > 0, "Confirm support for approved facts."),
        )
        next_action = next(
            (message for blocked, message in blockers if blocked), "Phase 2 is ready."
        )
        ready = not any(blocked for blocked, _message in blockers)
        return ReadinessReport(
            ready,
            unresolved,
            sensitivity_unreviewed,
            stale,
            open_conflicts,
            unsupported_approved,
            latest_import_complete,
            profile_version,
            next_action,
        )
