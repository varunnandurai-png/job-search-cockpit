from pathlib import Path

from playwright.sync_api import Page, expect

from tests.support.web import assert_accessible_page, running_test_app


def test_primary_navigation_is_keyboard_reachable(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.keyboard.press("Tab")
        expect(page.locator(":focus")).to_have_attribute("href", "#main-content")
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Job Search Cockpit home")).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Home", exact=True)).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Review facts")).to_be_focused()


def test_five_primary_screens_have_semantic_structure_and_clean_console(
    page: Page, vault_settings
) -> None:
    console_problems: list[str] = []
    page.on(
        "console",
        lambda message: (
            console_problems.append(message.text) if message.type in {"error", "warning"} else None
        ),
    )
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        for path in ("/", "/review", "/search-profile", "/history"):
            page.goto(f"{running.base_url}{path}")
            assert_accessible_page(page)
        page.goto(f"{running.base_url}/")
        page.get_by_role("button", name="Import curated profile").click()
        assert_accessible_page(page)
        screenshot = Path("test-results") / "phase-1-import-preview.png"
        screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=screenshot, full_page=True)
    assert console_problems == []


def test_visible_controls_have_labels_and_focus_indicators(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.goto(f"{running.base_url}/search-profile")
        page.get_by_text("Create a new confirmed version").click()
        controls = page.locator("input:not([type=hidden]), textarea, select, button")
        for index in range(controls.count()):
            control = controls.nth(index)
            control.focus()
            assert control.evaluate(
                "el => Boolean(el.labels?.length || el.textContent?.trim() || "
                "el.getAttribute('aria-label'))"
            )
            assert control.evaluate(
                "el => { const s=getComputedStyle(el); return s.outlineStyle !== 'none' "
                "&& parseFloat(s.outlineWidth) >= 2; }"
            )


def test_validation_errors_are_announced(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.goto(f"{running.base_url}/search-profile")
        page.get_by_text("Create a new confirmed version").click()
        page.locator("#profile-reason").fill("Fixture reason")
        page.locator("#profile-confirmation").fill("WRONG")
        page.locator("#diff-digest").fill("0" * 64)
        page.get_by_role("button", name="Create new profile version").click()
        expect(page.locator('[role="alert"]')).to_be_visible()
