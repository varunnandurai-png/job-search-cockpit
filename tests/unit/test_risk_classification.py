import pytest

from job_search_cockpit.facts.conflicts import classify_risks, normalize_for_comparison
from job_search_cockpit.facts.types import RiskFlag
from job_search_cockpit.imports.types import CandidateClaim
from tests.support.builders import candidate


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        (candidate("metric.savings", "$5M annually"), RiskFlag.QUANTIFIED),
        (
            candidate(
                "employment.walmart.dates",
                "July 2021 \u2013 June 2024",
                category="dates",
            ),
            RiskFlag.DATE,
        ),
        (
            candidate(
                "employment.jpmorgan.title",
                "Senior Product Associate",
                category="title",
            ),
            RiskFlag.TITLE,
        ),
        (
            candidate("employment.jpmorgan.team_count", "5 scrum teams"),
            RiskFlag.TEAM_SCOPE,
        ),
    ],
)
def test_risky_claims_require_individual_review(
    claim: CandidateClaim,
    expected: RiskFlag,
) -> None:
    assert expected in classify_risks(claim)


def test_comparison_normalizes_dash_punctuation_but_preserves_numbers() -> None:
    first = candidate("metric.conversion", "Conversion improved 2\u20133% to 5\u20137%")
    equivalent = candidate("metric.conversion", "conversion improved 2-3% to 5-7%")
    different = candidate("metric.conversion", "conversion improved 2-3% to 6-8%")
    assert normalize_for_comparison(first) == normalize_for_comparison(equivalent)
    assert normalize_for_comparison(first) != normalize_for_comparison(different)
