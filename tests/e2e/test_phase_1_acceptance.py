from playwright.sync_api import Page, expect

from tests.support.web import assert_readiness_is_false, running_test_app


def test_phase_1_sanitized_dry_run(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        assert_readiness_is_false(page)

        page.get_by_role("button", name="Import curated profile").click()
        expect(page.get_by_text("Original files remain unchanged")).to_be_visible()
        page.goto(f"{running.base_url}/")
        assert_readiness_is_false(page)
        page.get_by_role("button", name="Import curated profile").click()
        page.get_by_role("button", name="Import curated profile").click()
        expect(page.get_by_text("Not ready for Phase 2")).to_be_visible()

        for _index in range(100):
            page.goto(f"{running.base_url}/review")
            links = page.locator("main ol > li > a")
            if links.count() == 0:
                break
            links.first.click()
            if page.get_by_role("heading", name="These sources disagree").count():
                page.locator('input[name="selected_revision_id"]').first.check()
                page.locator("#conflict-reason").fill("Sanitized acceptance decision")
                page.get_by_role("button", name="Resolve conflict").click()
            if page.locator("#sensitivity").count():
                page.locator("#sensitivity").select_option("normal")
                page.get_by_role("button", name="Save confidentiality").click()
            if page.get_by_role("button", name="Approve fact").count():
                page.get_by_role("button", name="Approve fact").click()
        else:
            raise AssertionError("Fixture review did not converge.")

        page.goto(f"{running.base_url}/")
        expect(page.get_by_text("Your verified profile is ready for Phase 2")).to_be_visible()
