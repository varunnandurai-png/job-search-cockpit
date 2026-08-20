import json
from pathlib import Path

import pytest

from job_search_cockpit.config import SourceKind, SourceSpec
from job_search_cockpit.facts.types import RiskFlag
from job_search_cockpit.imports.assessment import AssessmentImporter
from job_search_cockpit.imports.grammar import semantic_anchor
from job_search_cockpit.imports.master_profile import MasterProfileImporter
from job_search_cockpit.imports.profile_json import ProfileJsonImporter
from job_search_cockpit.imports.types import MalformedSourceError
from job_search_cockpit.imports.workflow import WorkflowImporter
from tests.support.builders import one


def test_profile_json_importer_keeps_exact_source_locator(profile_json_spec: SourceSpec) -> None:
    result = ProfileJsonImporter().read(profile_json_spec)
    claim = one(result.claims, canonical_key="employment.jpmorganchase.title")
    assert claim.display_value == "Senior Product Associate (Product Manager)"
    assert claim.evidence.locator == "$.experience[0].title"


def test_assessment_recommendations_do_not_become_career_facts(
    assessment_spec: SourceSpec,
) -> None:
    result = AssessmentImporter().read(assessment_spec)
    assert not any(claim.canonical_key.startswith("employment.") for claim in result.claims)
    assert result.search_profile is not None
    assert result.search_profile.location_allocation == {
        "Hyderabad": 40,
        "Bengaluru": 45,
        "Singapore": 15,
    }


def test_reordering_bullets_does_not_change_claim_identity(profile_json_spec: SourceSpec) -> None:
    original = ProfileJsonImporter().read(profile_json_spec)
    payload = json.loads(profile_json_spec.path.read_text(encoding="utf-8"))
    payload["experience"][0]["bullets"].reverse()
    profile_json_spec.path.write_text(json.dumps(payload), encoding="utf-8")
    reordered = ProfileJsonImporter().read(profile_json_spec)
    assert {claim.canonical_key for claim in reordered.claims} == {
        claim.canonical_key for claim in original.claims
    }


def test_contact_and_internal_metrics_are_potentially_confidential(
    profile_json_spec: SourceSpec,
) -> None:
    result = ProfileJsonImporter().read(profile_json_spec)
    email = one(result.claims, canonical_key="contact.email")
    metric = one(
        result.claims,
        canonical_key="employment.example-commerce.led-last-mile-platform-modernization-supporting-annual-gmv",
    )
    assert RiskFlag.POTENTIALLY_CONFIDENTIAL in email.declared_risks
    assert RiskFlag.POTENTIALLY_CONFIDENTIAL in metric.declared_risks


def test_master_profile_parses_unicode_dashes_and_employer_attribution(
    master_profile_spec: SourceSpec,
) -> None:
    result = MasterProfileImporter().read(master_profile_spec)
    title = one(result.claims, canonical_key="employment.jpmorganchase.title")
    assert title.employer_key == "jpmorganchase"
    assert title.period_start is not None
    assert title.period_end is None


def test_workflow_creates_policy_claims_not_achievements(resume_workflow_spec: SourceSpec) -> None:
    result = WorkflowImporter().read(resume_workflow_spec)
    assert result.claims
    assert all(claim.category == "policy" for claim in result.claims)
    assert not any(claim.canonical_key.startswith("employment.") for claim in result.claims)


def test_malformed_json_is_rejected_without_partial_claims(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text('{"experience": [', encoding="utf-8")
    spec = SourceSpec("profile_json", SourceKind.PROFILE_JSON, path)
    with pytest.raises(MalformedSourceError):
        ProfileJsonImporter().read(spec)


def test_semantic_anchor_excludes_mutable_dates_and_results() -> None:
    first = "Launched Home Search in June 2024, improving conversion to 5%."
    changed = "Launched Home Search in July 2025 — improving conversion to 7%."
    assert semantic_anchor(first) == semantic_anchor(changed)
