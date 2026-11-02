"""Every view of milestone 4 at 200 % zoom: a 1280 pixel screen is then 640 wide, with the text twice its size."""

import pytest

from tests.demo.support import until
from tests.helpers import overflows_sideways

VIEWS = [
    "/equipment?status=stopped",
    "/planning?panel=shown",
    "/board?location=Roof",
    "/planning?show=timeline&location=Roof",
    "/calendar?view=week&date=2026-10-28&location=Roof",
    "/calendar?view=month&date=2026-10-28&location=Roof",
]


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.parametrize("path", VIEWS)
def test_each_view_works_at_twice_the_size(open_filled, path):
    page = open_filled(path, width=640, layout={"list_density": "dense", "page_title": "header"})
    if "calendar" in path:
        until(page, "document.documentElement.dataset.calendarReady !== undefined")
    assert not overflows_sideways(page)
    assert page.locator("h1").is_visible()
