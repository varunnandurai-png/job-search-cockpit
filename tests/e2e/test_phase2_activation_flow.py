from playwright.sync_api import Page, expect

from tests.support.web import running_test_app


def test_phase2_activation_page_is_keyboard_accessible(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.get_by_role("link", name="Phase II").press("Enter")
        expect(page.get_by_role("heading", name="Phase II activation")).to_be_visible()
        expect(page.get_by_text("No job sources have been contacted")).to_be_visible()
