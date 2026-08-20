import pytest
from playwright.sync_api import Page

from tests.support.web import running_test_app


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_home_has_no_horizontal_scroll(page: Page, vault_settings, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )


def test_design_tokens_have_required_contrast_and_target_size(page: Page, vault_settings) -> None:
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        body = page.locator("body")
        assert body.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(245, 245, 247)"
        assert body.evaluate("el => getComputedStyle(el).color") == "rgb(29, 29, 31)"
        button = page.get_by_role("button", name="Import curated profile")
        assert button.bounding_box()["height"] >= 44


def test_reduced_motion_and_two_hundred_percent_reflow(page: Page, vault_settings) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 390, "height": 700})
    with running_test_app(vault_settings) as running:
        page.goto(running.launch_url)
        page.evaluate("document.documentElement.style.zoom = '2'")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert (
            page.locator("body").evaluate(
                "el => getComputedStyle(el).getPropertyValue('--motion-duration').trim()"
            )
            == "0ms"
        )
