import pytest

from job_search_cockpit.phase1_contract.retrieval import (
    RetrievalCandidate,
    retrieve_matching_candidates,
)
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
)


def _requirement(
    requirement_id: str,
    *,
    capability_ids: tuple[str, ...] = ("capability.product_delivery",),
) -> Phase1MatchingRequirementPredicate:
    return Phase1MatchingRequirementPredicate(
        requirement_id=requirement_id,
        component="responsibility",
        modality="required",
        capability_ids=capability_ids,
    )


def _query(
    requirements: tuple[Phase1MatchingRequirementPredicate, ...],
) -> Phase1MatchingRequirementQuery:
    return Phase1MatchingRequirementQuery(
        requirement_ids=tuple(item.requirement_id for item in requirements),
        job_revision_id="job-revision-1",
        coverage_ledger_fingerprint="a" * 64,
        launch_session_fingerprint="b" * 64,
        requirements=requirements,
    )


def _candidate(
    index: int,
    wording: str,
    *,
    canonical_key: str | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        canonical_key=canonical_key or f"skills.product-delivery-{index:02d}",
        claim_id=f"claim-{index:02d}",
        revision_id=f"revision-{index:02d}",
        support_assertion_id=f"support-{index:02d}",
        category="skill",
        subject="Example",
        safe_wording=wording,
        employer_key="example",
        period_start=None,
        period_end=None,
    )


def test_query_rejects_unknown_taxonomy_and_canonical_fact_keys() -> None:
    with pytest.raises(ValueError, match="controlled taxonomy"):
        _requirement("job.required.1", capability_ids=("skills.python",))

    with pytest.raises(ValueError, match="controlled taxonomy"):
        _requirement("job.required.1", capability_ids=("capability.user supplied text",))

    with pytest.raises(ValueError, match="at least one controlled taxonomy"):
        _requirement("job.required.1", capability_ids=())


def test_retrieval_selects_only_controlled_relevance_in_stable_order() -> None:
    query = _query((_requirement("job.required.1"),))
    candidates = (
        _candidate(
            2,
            "Owned annual compensation reviews.",
            canonical_key="education.example-degree",
        ),
        _candidate(1, "Led product delivery across two release trains."),
        _candidate(
            0,
            "Owned product delivery for a platform.",
            canonical_key="skills.alpha.product-delivery-00",
        ),
    )

    result = retrieve_matching_candidates(query, candidates)

    assert result.complete is True
    assert tuple(item.canonical_key for item in result.choices) == (
        "skills.alpha.product-delivery-00",
        "skills.product-delivery-01",
    )
    assert tuple(edge.requirement_id for edge in result.edges) == (
        "job.required.1",
        "job.required.1",
    )
    assert all(
        edge.matched_taxonomy_ids == ("capability.product_delivery",)
        for edge in result.edges
    )


def test_retrieval_caps_choices_and_edges_and_marks_manifest_incomplete() -> None:
    requirements = tuple(_requirement(f"job.required.{index:02d}") for index in range(1, 33))
    query = _query(requirements)
    candidates = tuple(
        _candidate(index, f"Product delivery ownership for release {index}.")
        for index in range(33)
    )

    result = retrieve_matching_candidates(query, candidates)

    assert result.complete is False
    assert len(result.choices) == 32
    assert len(result.edges) == 96
    assert result.omission_reason_counts == (
        ("relevant_choice_cap_exceeded", 1),
        ("relevance_edge_cap_exceeded", 960),
    )


def test_retrieval_never_uses_wording_and_fails_closed_for_unknown_identifiers() -> None:
    query = _query((_requirement("job.required.1"),))
    candidate = _candidate(
        1,
        "Led product delivery across two release trains.",
        canonical_key="employment.example.unclassified-fact",
    )

    result = retrieve_matching_candidates(query, (candidate,))

    assert result.complete is False
    assert result.choices == ()
    assert result.examined_count == 1
    assert result.omission_reason_counts == (("semantic_candidate_unclassified", 1),)


def test_legacy_query_without_semantic_predicates_is_incomplete() -> None:
    query = Phase1MatchingRequirementQuery(requirement_ids=("skills.python",))

    result = retrieve_matching_candidates(
        query,
        (_candidate(1, "Python product delivery."),),
    )

    assert result.complete is False
    assert result.choices == ()
    assert result.omission_reason_counts == (("semantic_predicates_missing", 1),)
