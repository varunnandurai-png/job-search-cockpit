from datetime import UTC, datetime

import pytest

from job_search_cockpit.phase2.assessment_types import RequirementKind, ScoringComponent
from job_search_cockpit.phase2.candidates import (
    CandidateWorkflowUnavailable,
    extract_public_requirements,
)
from job_search_cockpit.phase2.models import Phase2JobRevision


def _revision(description: str) -> Phase2JobRevision:
    return Phase2JobRevision(
        id="revision-1",
        job_record_id="job-1",
        source_observation_id="observation-1",
        canonical_url="https://jobs.example.test/1",
        title="Senior Product Manager",
        employer_name="Example",
        locations_json=["Hyderabad"],
        posted_at=None,
        public_description=description,
        compensation_text=None,
        content_fingerprint="a" * 64,
        created_at=datetime(2026, 8, 31, tzinfo=UTC),
    )


def test_extraction_assigns_stable_public_ids_and_exact_spans() -> None:
    revision = _revision("You will own the product roadmap. Python is required.")

    first = extract_public_requirements(revision)
    second = extract_public_requirements(revision)

    assert first == second
    assert all(item.requirement_id.startswith("job.revision-1.requirement.") for item in first)
    assert [item.source_span_id for item in first] == [
        "job.revision-1.span.0",
        "job.revision-1.span.1",
    ]
    assert first[0].kind is RequirementKind.MATERIAL_RESPONSIBILITY
    assert first[1].kind is RequirementKind.REQUIRED


def test_ambiguous_clause_is_conservative_and_blocks_manual_scoring() -> None:
    requirements = extract_public_requirements(_revision("Bring a thoughtful approach."))

    assert requirements[0].kind is RequirementKind.REQUIRED
    assert requirements[0].component is ScoringComponent.EVIDENCE


def test_extraction_refuses_missing_public_description() -> None:
    with pytest.raises(CandidateWorkflowUnavailable, match="description"):
        extract_public_requirements(_revision(""))


def test_extraction_blocks_a_listing_with_more_than_thirty_two_clauses() -> None:
    description = ". ".join(f"Requirement {index} is required" for index in range(33)) + "."

    with pytest.raises(CandidateWorkflowUnavailable, match="32"):
        extract_public_requirements(_revision(description))


def test_bounded_extraction_caps_at_thirty_two_for_long_listings() -> None:
    description = ". ".join(f"Requirement {index} is required" for index in range(45)) + "."
    requirements = extract_public_requirements(_revision(description), bounded=True)

    assert len(requirements) == 32
    assert all(item.requirement_id.startswith("job.revision-1.requirement.") for item in requirements)
