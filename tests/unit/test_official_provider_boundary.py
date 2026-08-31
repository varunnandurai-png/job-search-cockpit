from importlib.util import find_spec


def test_approved_apify_jsearch_provider_modules_are_importable() -> None:
    assert find_spec("job_search_cockpit.phase2.providers") is not None
    assert find_spec("job_search_cockpit.phase2.provider_config") is not None
