from playwright.sync_api import Page, expect

from tests.support.web import running_test_app


def test_phase2_activation_page_is_keyboard_accessible(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.get_by_role("link", name="Phase II").press("Enter")
        expect(page.get_by_role("heading", name="Phase II activation")).to_be_visible()
        expect(page.get_by_text("No job sources have been contacted")).to_be_visible()


def test_assessment_page_renders_the_redacted_authority_state(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.goto(f"{running.base_url}/phase-2/assessments")

        expect(page.get_by_role("heading", name="Match assessments")).to_be_visible()
        expect(page.get_by_text("Current match assessments are unavailable.")).to_be_visible()
        expect(page.locator("form")).to_have_count(0)
