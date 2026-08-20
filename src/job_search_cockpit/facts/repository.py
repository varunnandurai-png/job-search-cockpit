from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from job_search_cockpit.storage.models import Claim, ClaimEvidence, ClaimRevision


@dataclass(frozen=True, slots=True)
class FactDetail:
    claim: Claim
    revisions: tuple[ClaimRevision, ...]
    evidence: tuple[ClaimEvidence, ...]


class FactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, claim_id: str) -> FactDetail | None:
        claim = self.session.get(Claim, claim_id)
        if claim is None:
            return None
        revisions = tuple(
            self.session.scalars(
                select(ClaimRevision)
                .where(ClaimRevision.claim_id == claim_id)
                .order_by(ClaimRevision.created_at)
            )
        )
        revision_ids = [revision.id for revision in revisions]
        evidence = tuple(
            self.session.scalars(
                select(ClaimEvidence).where(ClaimEvidence.revision_id.in_(revision_ids))
            )
        )
        return FactDetail(claim, revisions, evidence)

    def queue(self) -> tuple[Claim, ...]:
        return tuple(
            self.session.scalars(
                select(Claim).order_by(Claim.stale.desc(), Claim.category, Claim.canonical_key)
            )
        )
