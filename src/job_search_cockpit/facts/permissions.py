from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.storage.models import (
    AuditEvent,
    Claim,
    ClaimRevision,
    ConfidentialPermissionEvent,
    NamedUse,
)
from job_search_cockpit.storage.mutation import MutationCoordinator


class PermissionError(ValueError):
    """Raised when a confidential-use permission command is invalid."""


class PermissionVersionConflict(PermissionError):
    """Raised when a permission command was based on stale state."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _audit(session: Session, event: ConfidentialPermissionEvent, summary: str) -> None:
    session.add(
        AuditEvent(
            id=str(uuid4()),
            event_type=f"confidential_permission_{event.event_type}",
            area="permissions",
            subject_id=event.permission_id,
            summary=summary,
            after_json={
                "event_id": event.id,
                "event_version": event.event_version,
                "claim_id": event.claim_id,
                "revision_id": event.revision_id,
                "named_use_id": event.named_use_id,
                "expires_at": event.expires_at.isoformat() if event.expires_at else None,
            },
            sensitive=True,
            reason=event.reason,
        )
    )


class NamedUseService:
    def __init__(self, coordinator: MutationCoordinator) -> None:
        self.coordinator = coordinator

    def create(self, kind: str, external_reference: str, description: str, actor: str) -> NamedUse:
        values = (kind.strip(), external_reference.strip(), description.strip(), actor.strip())
        if not all(values):
            raise PermissionError("Named-use fields are required.")

        def create_one(session: Session) -> NamedUse:
            existing = session.scalar(
                select(NamedUse).where(
                    NamedUse.kind == values[0],
                    NamedUse.external_reference == values[1],
                    NamedUse.description == values[2],
                )
            )
            if existing is not None:
                return existing
            named_use = NamedUse(
                id=str(uuid4()),
                kind=values[0],
                external_reference=values[1],
                description=values[2],
                creator=values[3],
            )
            session.add(named_use)
            session.add(
                AuditEvent(
                    id=str(uuid4()),
                    event_type="named_use_created",
                    area="permissions",
                    subject_id=named_use.id,
                    summary="A named use was created.",
                    after_json={"kind": named_use.kind, "reference": named_use.external_reference},
                    sensitive=False,
                )
            )
            return named_use

        return self.coordinator.run(create_one, "create_named_use", expected_version=None)


class PermissionService:
    CONFIRMATION = "GRANT CONFIDENTIAL USE"

    def __init__(self, coordinator: MutationCoordinator) -> None:
        self.coordinator = coordinator

    @staticmethod
    def _latest(
        session: Session, event: ConfidentialPermissionEvent
    ) -> ConfidentialPermissionEvent:
        latest = session.scalar(
            select(ConfidentialPermissionEvent)
            .where(ConfidentialPermissionEvent.permission_id == event.permission_id)
            .order_by(ConfidentialPermissionEvent.event_version.desc())
        )
        if latest is None:
            raise PermissionError("The permission does not exist.")
        return latest

    @staticmethod
    def _check_current(
        session: Session, event_id: str, expected_event_version: int
    ) -> ConfidentialPermissionEvent:
        event = session.get(ConfidentialPermissionEvent, event_id)
        if event is None:
            raise PermissionError("The permission event does not exist.")
        latest = PermissionService._latest(session, event)
        if latest.id != event.id or latest.event_version != expected_event_version:
            raise PermissionVersionConflict("This permission changed in another action.")
        if latest.event_type not in {"grant", "supersede"}:
            raise PermissionError("The permission is no longer active.")
        return latest

    @staticmethod
    def _append(
        session: Session,
        prior: ConfidentialPermissionEvent,
        event_type: str,
        actor: str,
        reason: str,
        *,
        named_use_id: str | None = None,
        confirmation: str = "",
        expires_at: datetime | None = None,
    ) -> ConfidentialPermissionEvent:
        event = ConfidentialPermissionEvent(
            id=str(uuid4()),
            permission_id=prior.permission_id,
            event_type=event_type,
            event_version=prior.event_version + 1,
            claim_id=prior.claim_id,
            revision_id=prior.revision_id,
            named_use_id=named_use_id or prior.named_use_id,
            actor=actor,
            confirmation=confirmation,
            reason=reason,
            target_event_id=prior.id,
            expires_at=expires_at,
        )
        session.add(event)
        _audit(session, event, f"Confidential-use permission {event_type} recorded.")
        return event

    def grant(
        self,
        claim_id: str,
        revision_id: str,
        named_use_id: str,
        actor: str,
        confirmation: str,
        expires_at: datetime | None,
        expected_event_version: int,
    ) -> ConfidentialPermissionEvent:
        if expected_event_version != 0:
            raise PermissionVersionConflict("A new permission must start at version zero.")
        if confirmation != self.CONFIRMATION:
            raise PermissionError("Type the exact confidential-use confirmation phrase.")

        def grant_one(session: Session) -> ConfidentialPermissionEvent:
            claim = session.get(Claim, claim_id)
            revision = session.get(ClaimRevision, revision_id)
            named_use = session.get(NamedUse, named_use_id)
            if claim is None or revision is None or revision.claim_id != claim.id:
                raise PermissionError("The exact fact revision does not exist.")
            if claim.active_revision_id != revision.id:
                raise PermissionError("Only the active fact revision can be permitted.")
            if named_use is None:
                raise PermissionError("The named use does not exist.")
            event = ConfidentialPermissionEvent(
                id=str(uuid4()),
                permission_id=str(uuid4()),
                event_type="grant",
                event_version=1,
                claim_id=claim.id,
                revision_id=revision.id,
                named_use_id=named_use.id,
                actor=actor.strip(),
                confirmation=confirmation,
                reason="Explicit confidential-use grant",
                target_event_id=None,
                expires_at=expires_at,
            )
            session.add(event)
            _audit(session, event, "Confidential-use permission granted.")
            return event

        return self.coordinator.run(grant_one, "grant_confidential_use", expected_event_version)

    def revoke(
        self, permission_event_id: str, actor: str, reason: str, expected_event_version: int
    ) -> ConfidentialPermissionEvent:
        if not reason.strip():
            raise PermissionError("A revocation reason is required.")

        def revoke_one(session: Session) -> ConfidentialPermissionEvent:
            prior = self._check_current(session, permission_event_id, expected_event_version)
            return self._append(session, prior, "revoke", actor, reason.strip())

        return self.coordinator.run(revoke_one, "revoke_confidential_use", expected_event_version)

    def expire(
        self, permission_event_id: str, actor: str, reason: str, expected_event_version: int
    ) -> ConfidentialPermissionEvent:
        if not reason.strip():
            raise PermissionError("An expiry reason is required.")

        def expire_one(session: Session) -> ConfidentialPermissionEvent:
            prior = self._check_current(session, permission_event_id, expected_event_version)
            return self._append(session, prior, "expire", actor, reason.strip())

        return self.coordinator.run(expire_one, "expire_confidential_use", expected_event_version)

    def supersede(
        self,
        permission_event_id: str,
        replacement_named_use_id: str,
        actor: str,
        confirmation: str,
        expires_at: datetime | None,
        expected_event_version: int,
    ) -> ConfidentialPermissionEvent:
        if confirmation != self.CONFIRMATION:
            raise PermissionError("Type the exact confidential-use confirmation phrase.")

        def supersede_one(session: Session) -> ConfidentialPermissionEvent:
            prior = self._check_current(session, permission_event_id, expected_event_version)
            if session.get(NamedUse, replacement_named_use_id) is None:
                raise PermissionError("The replacement named use does not exist.")
            return self._append(
                session,
                prior,
                "supersede",
                actor,
                "Confidential-use permission superseded",
                named_use_id=replacement_named_use_id,
                confirmation=confirmation,
                expires_at=expires_at,
            )

        return self.coordinator.run(
            supersede_one, "supersede_confidential_use", expected_event_version
        )

    def expire_due(
        self, now: datetime, actor: str = "system"
    ) -> Sequence[ConfidentialPermissionEvent]:
        instant = _aware(now)

        def expire_all(session: Session) -> Sequence[ConfidentialPermissionEvent]:
            candidates = tuple(
                session.scalars(
                    select(ConfidentialPermissionEvent)
                    .where(ConfidentialPermissionEvent.event_type.in_(("grant", "supersede")))
                    .order_by(
                        ConfidentialPermissionEvent.permission_id,
                        ConfidentialPermissionEvent.event_version.desc(),
                    )
                )
            )
            latest_by_permission: dict[str, ConfidentialPermissionEvent] = {}
            for candidate in candidates:
                latest_by_permission.setdefault(candidate.permission_id, candidate)
            expired: list[ConfidentialPermissionEvent] = []
            for candidate in latest_by_permission.values():
                if candidate.expires_at is not None and _aware(candidate.expires_at) <= instant:
                    expired.append(
                        self._append(
                            session,
                            candidate,
                            "expire",
                            actor,
                            "Permission expiry time reached",
                        )
                    )
            return tuple(expired)

        return self.coordinator.run(expire_all, "expire_due_permissions", expected_version=None)
