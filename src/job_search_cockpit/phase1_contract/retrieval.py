from __future__ import annotations

import re
from dataclasses import dataclass

from job_search_cockpit.phase1_contract.snapshots import (
    Phase1MatchingRequirementPredicate,
    Phase1MatchingRequirementQuery,
)

_CHOICE_CAP = 32
_EDGE_CAP = 96

# Frozen v1 classification corpus. Rules inspect only canonical identifiers that
# were already reviewed in Phase I; safe wording never drives retrieval.
_TERMS: dict[str, tuple[tuple[str, ...], ...]] = {
    "capability.applied_ai": (("applied", "ai"), ("artificial", "intelligence")),
    "capability.cross_functional_leadership": (("cross", "functional"),),
    "capability.data_analytics": (("data", "analytics"), ("analytics",)),
    "capability.lifecycle_management": (("lifecycle",), ("life", "cycle")),
    "capability.partner_integration": (("partner", "integration"),),
    "capability.platform_product": (("platform", "product"),),
    "capability.product_delivery": (("product", "delivery"),),
    "capability.product_discovery": (("product", "discovery"),),
    "capability.product_strategy": (("product", "strategy"),),
    "capability.roadmap_prioritization": (("roadmap",), ("prioritization",)),
    "capability.stakeholder_influence": (("stakeholder",), ("influence",)),
    "responsibility.delivery_ownership": (("delivery", "ownership"),),
    "responsibility.discovery_ownership": (("discovery", "ownership"),),
    "responsibility.executive_influence": (("executive", "influence"),),
    "responsibility.kpi_ownership": (("kpi",), ("metric", "ownership")),
    "responsibility.people_leadership": (("people", "leadership"),),
    "responsibility.product_decisions": (("product", "decision"),),
    "responsibility.roadmap_ownership": (("roadmap", "ownership"),),
    "responsibility.technical_tradeoffs": (("technical", "tradeoff"),),
    "domain.applied_ai": (("applied", "ai"),),
    "domain.banking": (("banking",), ("bank",)),
    "domain.billing": (("billing",),),
    "domain.commerce": (("commerce",),),
    "domain.decision_support": (("decision", "support"),),
    "domain.ecommerce": (("ecommerce",), ("e", "commerce")),
    "domain.fintech": (("fintech",),),
    "domain.fraud": (("fraud",),),
    "domain.fulfilment": (("fulfilment",), ("fulfillment",)),
    "domain.home_buying": (("home", "buying"),),
    "domain.last_mile": (("last", "mile"),),
    "domain.lending": (("lending",), ("loan",)),
    "domain.mortgage": (("mortgage",),),
    "domain.omnichannel": (("omnichannel",), ("omni", "channel")),
    "domain.payments": (("payment",), ("payments",)),
    "domain.risk": (("risk",),),
    "domain.subscriptions": (("subscription",), ("subscriptions",)),
    "technical_object.ai": (("ai",), ("artificial", "intelligence")),
    "technical_object.analytics": (("analytics",),),
    "technical_object.api": (("api",), ("apis",)),
    "technical_object.data": (("data",),),
    "technical_object.integration": (("integration",), ("integrations",)),
    "technical_object.platform": (("platform",),),
    "technical_object.system": (("system",), ("systems",)),
    "outcome_scale.adoption": (("adoption",),),
    "outcome_scale.commercial": (("commercial",), ("revenue",)),
    "outcome_scale.enterprise": (("enterprise",),),
    "outcome_scale.kpi": (("kpi",), ("metric",)),
    "outcome_scale.operational_complexity": (("operational", "complexity"),),
    "outcome_scale.regulated": (("regulated",), ("regulatory",)),
    "role_profile.applied_ai_product_manager": (("applied", "ai", "product"),),
    "role_profile.principal_product_manager_ic": (("principal", "product"),),
    "role_profile.senior_product_manager": (("senior", "product"),),
    "role_profile.technical_product_manager": (("technical", "product"),),
}

_KNOWN_NON_MATCHING_PREFIXES = (
    "application.",
    "contact.",
    "education.",
    "policy.",
    "profile.contact.",
)


@dataclass(frozen=True)
class RetrievalCandidate:
    canonical_key: str
    claim_id: str
    revision_id: str
    support_assertion_id: str
    category: str
    subject: str
    safe_wording: str
    employer_key: str | None
    period_start: str | None
    period_end: str | None


@dataclass(frozen=True, slots=True)
class RetrievalEdge:
    requirement_id: str
    claim_id: str
    matched_taxonomy_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    choices: tuple[RetrievalCandidate, ...]
    edges: tuple[RetrievalEdge, ...]
    candidate_universe_count: int
    examined_count: int
    omission_reason_counts: tuple[tuple[str, int], ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class CandidateClassification:
    known: bool
    taxonomy_ids: tuple[str, ...]


def classify_candidate(candidate: RetrievalCandidate) -> CandidateClassification:
    canonical_key = candidate.canonical_key.casefold()
    if canonical_key.startswith(_KNOWN_NON_MATCHING_PREFIXES):
        return CandidateClassification(True, ())
    tokens = frozenset(re.findall(r"[a-z0-9]+", canonical_key))
    taxonomy_ids = tuple(
        taxonomy_id
        for taxonomy_id, patterns in _TERMS.items()
        if any(set(pattern) <= tokens for pattern in patterns)
    )
    return CandidateClassification(bool(taxonomy_ids), taxonomy_ids)


def _matches_constraints(
    requirement: Phase1MatchingRequirementPredicate,
    candidate: RetrievalCandidate,
) -> bool:
    if requirement.employer_constraint == "attributed" and not candidate.employer_key:
        return False
    if requirement.period_constraint == "dated" and not (
        candidate.period_start or candidate.period_end
    ):
        return False
    if requirement.period_constraint == "open_ended":
        return candidate.period_start is not None and candidate.period_end is None
    return True


def matched_taxonomy_ids(
    requirement: Phase1MatchingRequirementPredicate,
    candidate: RetrievalCandidate,
) -> tuple[str, ...]:
    if not _matches_constraints(requirement, candidate):
        return ()
    classification = classify_candidate(candidate)
    if not classification.known:
        return ()
    candidate_ids = set(classification.taxonomy_ids)
    return tuple(
        taxonomy_id
        for taxonomy_id in requirement.taxonomy_ids()
        if taxonomy_id in candidate_ids
    )


def is_relevant_candidate(
    query: Phase1MatchingRequirementQuery,
    candidate: RetrievalCandidate,
) -> bool:
    return any(matched_taxonomy_ids(requirement, candidate) for requirement in query.requirements)


def retrieve_matching_candidates(
    query: Phase1MatchingRequirementQuery,
    candidates: tuple[RetrievalCandidate, ...],
) -> RetrievalResult:
    if not query.requirements:
        return RetrievalResult((), (), 0, 0, (("semantic_predicates_missing", 1),), False)

    ordered = tuple(sorted(candidates, key=lambda item: (item.canonical_key, item.claim_id)))
    relevant: list[RetrievalCandidate] = []
    all_edges: list[RetrievalEdge] = []
    unclassified_count = 0
    for candidate in ordered:
        if not classify_candidate(candidate).known:
            unclassified_count += 1
            continue
        candidate_edges: list[RetrievalEdge] = []
        for requirement in query.requirements:
            taxonomy_ids = matched_taxonomy_ids(requirement, candidate)
            if taxonomy_ids:
                candidate_edges.append(
                    RetrievalEdge(requirement.requirement_id, candidate.claim_id, taxonomy_ids)
                )
        if candidate_edges:
            relevant.append(candidate)
            all_edges.extend(candidate_edges)

    omissions: list[tuple[str, int]] = []
    if unclassified_count:
        omissions.append(("semantic_candidate_unclassified", unclassified_count))
    if len(relevant) > _CHOICE_CAP:
        omissions.append(("relevant_choice_cap_exceeded", len(relevant) - _CHOICE_CAP))
    if len(all_edges) > _EDGE_CAP:
        omissions.append(("relevance_edge_cap_exceeded", len(all_edges) - _EDGE_CAP))
    return RetrievalResult(
        choices=tuple(relevant[:_CHOICE_CAP]),
        edges=tuple(all_edges[:_EDGE_CAP]),
        candidate_universe_count=len(relevant),
        examined_count=len(relevant) + unclassified_count,
        omission_reason_counts=tuple(omissions),
        complete=not omissions,
    )


__all__ = [
    "CandidateClassification",
    "RetrievalCandidate",
    "RetrievalEdge",
    "RetrievalResult",
    "classify_candidate",
    "is_relevant_candidate",
    "matched_taxonomy_ids",
    "retrieve_matching_candidates",
]
