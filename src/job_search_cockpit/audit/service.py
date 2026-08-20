from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.storage.models import AuditEvent


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(
        self, area: str | None = None, subject_id: str | None = None
    ) -> tuple[AuditEvent, ...]:
        statement = select(AuditEvent)
        if area is not None:
            statement = statement.where(AuditEvent.area == area)
        if subject_id is not None:
            statement = statement.where(AuditEvent.subject_id == subject_id)
        return tuple(self.session.scalars(statement.order_by(AuditEvent.created_at.desc())))

    def get(self, event_id: str) -> AuditEvent | None:
        return self.session.get(AuditEvent, event_id)
