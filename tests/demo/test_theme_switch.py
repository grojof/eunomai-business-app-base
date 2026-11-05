"""The scans open a page in the light theme and switch it to the dark one, instead of loading it twice. Here, on the
pages with the most kinds of content, the switched page paints as the page loaded dark."""

import pytest

from tests.demo.support import until
from tests.helpers import ANIMATIONS_FINISHED, TO_DARK

PAINT = """() => {
    const keys = ["color", "background-color", "border-top-color", "border-left-color", "outline-color", "fill",
                  "stroke", "opacity", "box-shadow", "text-decoration-color", "caret-color"];
    const styles = [...document.querySelectorAll("body *")]
        .filter((element) => element.checkVisibility({visibilityProperty: true}))
        .filter((element) => !element.closest("[data-preferences$='-theme'] summary svg"))
        .map((element) => {
            const style = getComputedStyle(element);
            return `${element.tagName}#${element.id} ${keys.map((key) => style.getPropertyValue(key)).join(" | ")}`;
        });
    const charts = [...document.querySelectorAll("canvas")].map((canvas) => {
        const chart = Chart.getChart(canvas);
        const scales = Object.values(chart.options.scales ?? {});
        const {legend, tooltip} = chart.options.plugins;
        return JSON.stringify([
            scales.map((scale) => [scale.grid?.color, scale.ticks?.color, scale.title?.color, scale.border?.color]),
            legend?.labels?.color, tooltip?.backgroundColor, tooltip?.titleColor, tooltip?.bodyColor,
            chart.data.datasets.map((set) => [set.backgroundColor, set.borderColor, set.pointBorderColor]),
        ]);
    });
    return {styles, charts};
}"""
"""What the scan reads: the colours of what is on screen, and the charts' own, which are drawn, not styled. The theme
control's picture of the theme in use is left out: it comes from the server, and the switch leaves it as it was."""
CHARTS_READY = "document.documentElement.dataset.chartsReady !== undefined"


@pytest.mark.browser
@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/equipment",
        "/calendar?view=month&date=2026-10-28",
        "/board?location=Roof",
        "/planning",
        "/planning?show=timeline",
        "/work-orders/1/edit",
        "/gallery/modal",
    ],
)
def test_a_page_switched_to_dark_paints_as_one_loaded_dark(open_filled, path):
    def painted(page):
        page.wait_for_load_state("networkidle")
        until(page, CHARTS_READY if page.locator("canvas").count() else "true")
        page.evaluate(ANIMATIONS_FINISHED)
        return page.evaluate(PAINT)

    loaded = painted(open_filled(path, theme="dark"))
    light = open_filled(path)
    painted(light)
    light.evaluate(TO_DARK)
    switched = painted(light)
    assert switched["charts"] == loaded["charts"]
    assert len(switched["styles"]) == len(loaded["styles"])
    assert [pair for pair in zip(switched["styles"], loaded["styles"], strict=True) if pair[0] != pair[1]] == []
