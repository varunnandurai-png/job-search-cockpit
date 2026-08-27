from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import Engine, case, desc, select
from sqlalchemy.orm import Session

from job_search_cockpit.phase2.assessment import (
    AssessmentAuthorityService,
    AssessmentAuthoritySnapshot,
    AssessmentUnavailable,
)
from job_search_cockpit.phase2.assessment_types import ConfidenceState
from job_search_cockpit.phase2.models import Phase2MatchAssessment, Phase2ShortlistDecision

_CONFIDENCE_ORDER = {
    ConfidenceState.HIGH: 0,
    ConfidenceState.MEDIUM: 1,
    ConfidenceState.LOW: 2,
    ConfidenceState.BLOCKED: 3,
}


@dataclass(frozen=True, slots=True)
class AssessmentReviewItem:
    """The narrow metadata set permitted in the local assessment review."""

    assessment_id: str
    score: int
    qualified_band: str
    confidence: ConfidenceState
    decision: str
    assessment_state: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not 1 <= len(self.assessment_id.strip()) <= 36:
            raise ValueError("assessment ID must fit persisted metadata")
        if not 0 <= self.score <= 100:
            raise ValueError("assessment score must be between zero and 100")
        if self.created_at.tzinfo is None:
            raise ValueError("assessment creation time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AssessmentReviewView:
    current: bool
    focused: tuple[AssessmentReviewItem, ...] = ()


class AssessmentReviewStore(Protocol):
    def current_items(
        self, snapshot: AssessmentAuthoritySnapshot
    ) -> tuple[AssessmentReviewItem, ...]: ...


class SqlAssessmentReviewStore:
    """Reads only current, opaque assessment metadata from the local catalog."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def current_items(
        self, snapshot: AssessmentAuthoritySnapshot
    ) -> tuple[AssessmentReviewItem, ...]:
        fields = snapshot.persistence_fields()
        assessment = Phase2MatchAssessment
        decision = Phase2ShortlistDecision
        fence = (
            assessment.phase1_profile_fingerprint == fields["phase1_profile_fingerprint"],
            assessment.phase1_profile_generation == fields["phase1_profile_generation"],
            assessment.phase1_readiness_fingerprint == fields["phase1_readiness_fingerprint"],
            assessment.phase1_readiness_generation == fields["phase1_readiness_generation"],
            assessment.phase1_authority_fingerprint == fields["phase1_authority_fingerprint"],
            assessment.phase1_authority_generation == fields["phase1_authority_generation"],
            assessment.phase1_restore_generation == fields["phase1_restore_generation"],
            assessment.phase2_activation_generation == fields["phase2_activation_generation"],
            assessment.phase2_restore_generation == fields["phase2_restore_generation"],
            decision.phase1_profile_fingerprint == fields["phase1_profile_fingerprint"],
            decision.phase1_profile_generation == fields["phase1_profile_generation"],
            decision.phase1_readiness_fingerprint == fields["phase1_readiness_fingerprint"],
            decision.phase1_readiness_generation == fields["phase1_readiness_generation"],
            decision.phase1_authority_fingerprint == fields["phase1_authority_fingerprint"],
            decision.phase1_authority_generation == fields["phase1_authority_generation"],
            decision.phase1_restore_generation == fields["phase1_restore_generation"],
            decision.phase2_activation_generation == fields["phase2_activation_generation"],
            decision.phase2_restore_generation == fields["phase2_restore_generation"],
        )
        confidence_order = case(
            (assessment.confidence == ConfidenceState.HIGH.value, 0),
            (assessment.confidence == ConfidenceState.MEDIUM.value, 1),
            (assessment.confidence == ConfidenceState.LOW.value, 2),
            else_=3,
        )
        statement = (
            select(
                assessment.id,
                assessment.total_score,
                assessment.qualified_band,
                assessment.confidence,
                decision.decision,
                assessment.assessment_state,
                assessment.created_at,
            )
            .join(decision, decision.match_assessment_id == assessment.id)
            .where(
                *fence,
                assessment.assessment_state.in_(("stable", "adjudicated")),
                assessment.qualified_band.in_(
                    ("strong", "worthwhile", "worthwhile_with_required_gap")
                ),
                assessment.total_score >= 70,
                assessment.confidence != ConfidenceState.BLOCKED.value,
                decision.decision == "focused",
            )
            .order_by(
                desc(assessment.total_score),
                confidence_order,
                desc(assessment.created_at),
                assessment.id,
            )
            .limit(20)
        )
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        return tuple(
            AssessmentReviewItem(
                assessment_id=row.id,
                score=row.total_score,
                qualified_band=row.qualified_band,
                confidence=ConfidenceState(row.confidence),
                decision=row.decision,
                assessment_state=row.assessment_state,
                created_at=row.created_at,
            )
            for row in rows
        )


class AssessmentReviewService:
    """Provides an authority-revalidated, non-sensitive assessment review state."""

    def __init__(
        self, authority_service: AssessmentAuthorityService, store: AssessmentReviewStore
    ) -> None:
        self._authority_service = authority_service
        self._store = store

    def current_view(self) -> AssessmentReviewView:
        try:
            captured = self._authority_service.capture_for_assessment()
            current = self._authority_service.revalidate_before_publication(captured)
            items = self._store.current_items(current)
        except AssessmentUnavailable:
            return AssessmentReviewView(current=False)
        return AssessmentReviewView(
            current=True,
            focused=tuple(
                item
                for item in items
                if item.decision == "focused"
                and item.assessment_state in {"stable", "adjudicated"}
                and item.qualified_band
                in {"strong", "worthwhile", "worthwhile_with_required_gap"}
                and item.confidence is not ConfidenceState.BLOCKED
                and item.score >= 70
            )[:20],
        )


@dataclass(frozen=True, slots=True)
class ShortlistCandidate:
    assessment_id: str
    score: int
    hard_gates_pass: bool = True
    official_source_current: bool = True
    assessment_current: bool = True
    qualified_band: str = "worthwhile"
    confidence: ConfidenceState = ConfidenceState.HIGH
    official_verified_at: datetime = field(
        default_factory=lambda: datetime.min.replace(tzinfo=UTC)
    )
    discovered_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))

    def __post_init__(self) -> None:
        if not self.assessment_id.strip():
            raise ValueError("assessment ID is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between zero and 100")
        if self.qualified_band not in {"strong", "worthwhile", "worthwhile_with_required_gap"}:
            raise ValueError("qualified band is not eligible for the focused shortlist")
        if self.official_verified_at.tzinfo is None or self.discovered_at.tzinfo is None:
            raise ValueError("shortlist timestamps must be timezone-aware")


def focused_shortlist(
    candidates: tuple[ShortlistCandidate, ...], *, limit: int = 20
) -> tuple[ShortlistCandidate, ...]:
    if not 1 <= limit <= 20:
        raise ValueError("focused shortlist limit must be between one and 20")
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.hard_gates_pass
        and candidate.official_source_current
        and candidate.assessment_current
        and candidate.confidence is not ConfidenceState.BLOCKED
        and candidate.score >= 70
    )
    ordered = sorted(
        eligible,
        key=lambda candidate: (
            -candidate.score,
            _CONFIDENCE_ORDER[candidate.confidence],
            -candidate.official_verified_at.timestamp(),
            -candidate.discovered_at.timestamp(),
            candidate.assessment_id,
        ),
    )
    return tuple(ordered[:limit])
