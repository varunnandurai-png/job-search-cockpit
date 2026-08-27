from importlib.util import find_spec


def test_retired_aggregator_modules_are_not_importable() -> None:
    assert find_spec("job_search_cockpit.phase2.providers") is None
    assert find_spec("job_search_cockpit.phase2.provider_config") is None
