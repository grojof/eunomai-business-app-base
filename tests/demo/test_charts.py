"""Charts in a real browser, on the dashboard and in the gallery."""

import json
import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import create_database_engine, exact_sum
from app.core.i18n import PSEUDO
from app.demo.charts import chart_examples
from app.demo.models import WorkOrder
from tests.demo.support import until
from tests.helpers import overflows_sideways, run_axe, untranslated

TYPES = ["bar", "stacked", "line", "area", "pie", "doughnut", "radar", "scatter", "bubble", "mixed"]
CHARTS_READY = "document.documentElement.dataset.chartsReady !== undefined"
ALLOWED = ("Business App", "Demo Person", "EQ-", "Cooling tower", "Air compressor", "Conveyor belt", "Forklift")
ALLOWED += ("Preventive plan", "Safety checks", "Oil change", "Filter replacement", "Belt replacement", "Calibration")
ALLOWED += ("Leak repair", "Electrical inspection")
ALLOWED += ("Standby generator", "Jan ", "Feb ", "Mar ", "Apr ", "May ", "Jun ", "Jul ", "Aug ", "Sep ", "Oct ")
ALLOWED += ("Nov ", "Dec ", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def tooltip_of(page, identifier, index=2):
    """Hovers over one mark and gives what the tooltip says, read from the chart."""
    page.locator(f"#{identifier}-summary").evaluate("element => element.scrollIntoView({block: 'start'})")
    page.evaluate("scrollBy(0, -90)")
    page.wait_for_timeout(350)  # marks are still moving into place
    position = page.evaluate(
        """([summary, index]) => {
            const canvas = document.getElementById(summary).closest('figure').querySelector('canvas');
            const chart = Chart.getChart(canvas);
            const element = chart.getDatasetMeta(0).data[index];
            const box = canvas.getBoundingClientRect();
            const { x, y } = element.tooltipPosition();
            return [box.left + x, box.top + y];
        }""",
        [f"{identifier}-summary", index],
    )
    page.mouse.move(*position)
    page.wait_for_timeout(120)
    return page.evaluate(
        """(summary) => {
            const chart = Chart.getChart(document.getElementById(summary).closest('figure').querySelector('canvas'));
            const tooltip = chart.tooltip;
            return { opacity: tooltip.opacity, title: tooltip.title, lines: tooltip.body.flatMap((b) => b.lines),
                     active: tooltip.getActiveElements().length };
        }""",
        f"{identifier}-summary",
    )


def test_the_dashboard_has_real_figures_from_the_rows(filled, filled_url):
    engine = create_database_engine(filled_url)
    with Session(engine) as session:
        expected = exact_sum(session.scalars(select(WorkOrder.cost)))
    engine.dispose()
    html = filled.get("/").text
    assert f"{expected:,.2f}" in html
    assert "Of 200 opened this year" in html
    assert html.count("data-chart ") == 3


def test_the_chart_counts_every_work_order(filled):
    html = filled.get("/").text
    config = json.loads(re.search(r'<script type="application/json">(.*?)</script>', html, re.S)[1])
    assert sum(int(value) for line in config["series"] for value in line["values"]) == 200


def test_the_dashboard_says_what_to_run_when_the_rows_are_not_there(client, person):
    html = client.get("/", headers=person).text
    assert "uv run --frozen python -m app.demo.generate" in html
    assert "1,250.75" in html
    assert "data-chart" not in html


def test_the_gallery_has_a_real_example_of_each_type(client, person):
    html = client.get("/gallery/chart", headers=person).text
    assert {figure.type for figure in chart_examples()} == set(TYPES)
    assert html.count('type="application/json"') == len(TYPES)
    assert "Our macro" in html


@pytest.mark.rule("LANG-01")
def test_no_text_outside_translation(filled, client, person):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get("/").text, ALLOWED) == []
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/gallery/chart", headers=person).text, ALLOWED) == []


@pytest.mark.parametrize("language", ["es", "ca"])
def test_month_labels_are_in_the_persons_language(client, person, language):
    client.cookies.set("language", language)
    html = client.get("/gallery/chart", headers=person).text
    assert ("ene" if language == "es" else "gen") in html


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.rule("A11Y-10")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_accessibility_failure_on_the_dashboard(open_filled, theme):
    page = open_filled("/", theme=theme, bypass_csp=True)
    until(page, CHARTS_READY)
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_no_detectable_failure_with_a_table_open(open_filled, theme):
    page = open_filled("/", theme=theme, bypass_csp=True)
    page.locator("figure summary").first.click()
    assert run_axe(page) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
def test_the_dashboard_fits_a_phone_with_longer_texts(open_filled):
    page = open_filled("/", language=PSEUDO, width=320)
    until(page, CHARTS_READY)
    assert not overflows_sideways(page)


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_every_type_draws_under_the_security_policy(open_page):
    problems = []
    page = open_page("/gallery/chart")
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.reload()
    until(page, CHARTS_READY)
    drawn = page.evaluate(
        "[...document.querySelectorAll('[data-chart-examples] canvas')].map((c) => Chart.getChart(c).config.type)"
    )
    assert drawn == ["bar", "bar", "line", "line", "pie", "doughnut", "radar", "scatter", "bubble", "bar"]
    assert problems == []


@pytest.mark.browser
def test_polar_area_draws_though_the_gallery_leaves_it_out(open_page):
    """A figure htmx brings is drawn too, so this adds one to the page as a screen would."""
    page = open_page("/gallery/chart", bypass_csp=True)
    until(page, CHARTS_READY)
    page.evaluate("""() => {
        const figure = document.querySelector('[data-chart]').cloneNode(true);
        const holder = document.createElement('div');
        const data = figure.querySelector('script');
        const fresh = figure.querySelector('canvas').cloneNode();
        figure.querySelector('canvas').replaceWith(fresh);
        data.textContent = JSON.stringify({ ...JSON.parse(data.textContent), type: 'polar' });
        holder.id = 'late-chart';
        holder.append(figure);
        document.body.append(holder);
        document.dispatchEvent(new CustomEvent('htmx:afterSettle', { detail: { target: holder } }));
    }""")
    until(page, "Chart.getChart(document.querySelector('#late-chart canvas'))?.config.type === 'polarArea'")


@pytest.mark.browser
def test_chart_js_loads_only_for_a_page_with_a_chart(open_page):
    page = open_page("/settings")
    page.wait_for_load_state("networkidle")
    assert page.evaluate("typeof Chart") == "undefined"


@pytest.mark.browser
def test_the_library_loads_with_its_integrity(open_page):
    page = open_page("/gallery/chart")
    until(page, CHARTS_READY)
    assert page.evaluate("document.querySelector('script[src*=umd]').integrity").startswith("sha384-")


@pytest.mark.browser
@pytest.mark.rule("A11Y-10")
def test_without_the_library_the_table_takes_over(open_page):
    page = open_page("/settings")
    page.route("**/chart.umd.min.js", lambda route: route.abort())
    page.goto(page.url.replace("/settings", "/gallery/chart"))
    until(page, "document.querySelector('[data-chart] details').open")
    assert not page.locator("[data-chart-box]").first.is_visible()
    assert page.locator("[data-chart] table").first.is_visible()


@pytest.mark.browser
@pytest.mark.rule("A11Y-10")
def test_without_javascript_the_summary_and_the_table_remain(open_page):
    page = open_page("/gallery/chart", javascript=False)
    figure = page.locator("[data-chart]").first
    assert not figure.locator("canvas").is_visible()
    figure.locator("summary").click()
    assert figure.locator("table").is_visible()


@pytest.mark.browser
def test_bars_and_lines_show_every_series_of_the_hovered_month_with_a_guide_line(open_page):
    page = open_page("/gallery/chart")
    until(page, CHARTS_READY)
    for identifier in ("example-bar", "example-stacked", "example-line", "example-area", "example-mixed"):
        tip = tooltip_of(page, identifier)
        assert tip["opacity"] > 0, identifier
        guide = page.evaluate(
            """(summary) => Chart.getChart(document.getElementById(summary).closest('figure').querySelector('canvas'))
                .options.plugins.guideLine.show""",
            f"{identifier}-summary",
        )
        assert guide is True


@pytest.mark.browser
def test_a_tooltip_names_each_series(open_page):
    page = open_page("/gallery/chart")
    until(page, CHARTS_READY)
    tip = tooltip_of(page, "example-bar")
    assert tip["title"] == ["Mar"]
    assert tip["lines"] == ["Planned: 300 h", "Worked: 310 h"]


@pytest.mark.browser
@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "37,500"), ("es", "37.500"), ("ca", "37.500")],
)
def test_numbers_in_tooltips_follow_the_language(open_page, language, expected):
    page = open_page("/gallery/chart", language=language)
    until(page, CHARTS_READY)
    assert expected in " ".join(tooltip_of(page, "example-area", 1)["lines"])


@pytest.mark.browser
def test_a_four_digit_number_follows_cldr_in_spanish(open_page):
    page = open_page("/gallery/chart", language="es")
    until(page, CHARTS_READY)
    assert page.evaluate("new Intl.NumberFormat(document.documentElement.lang).format(1250)") == "1250"


@pytest.mark.browser
def test_axes_follow_the_language(open_page):
    page = open_page("/gallery/chart", language="es")
    until(page, CHARTS_READY)
    ticks = page.evaluate(
        """Chart.getChart(document.getElementById('example-area-summary').closest('figure').querySelector('canvas'))
            .scales.y.ticks.map((tick) => tick.label)"""
    )
    assert any("mil" in label for label in ticks)


@pytest.mark.browser
@pytest.mark.parametrize("identifier", ["example-pie", "example-doughnut"])
def test_a_slice_grows_under_the_pointer(open_page, identifier):
    page = open_page("/gallery/chart")
    until(page, CHARTS_READY)
    tip = tooltip_of(page, identifier, 0)
    assert tip["active"] == 1
    offset = page.evaluate(
        """(summary) => Chart.getChart(document.getElementById(summary).closest('figure').querySelector('canvas'))
            .data.datasets[0].hoverOffset""",
        f"{identifier}-summary",
    )
    assert offset > 0


@pytest.mark.browser
@pytest.mark.parametrize(("identifier", "index"), [("example-scatter", 3), ("example-bubble", 4)])
def test_points_say_what_they_are(open_page, identifier, index):
    page = open_page("/gallery/chart")
    until(page, CHARTS_READY)
    tip = tooltip_of(page, identifier, index)
    assert tip["opacity"] > 0
    assert len(tip["lines"]) >= 3


@pytest.mark.browser
def test_colours_follow_a_change_of_theme_without_a_reload(open_page):
    page = open_page("/gallery/chart", theme="system")
    page.emulate_media(color_scheme="light")
    until(page, CHARTS_READY)
    read = """(() => {
        const chart = Chart.getChart(document.querySelector('[data-chart-examples] canvas'));
        return [chart.data.datasets[0].backgroundColor, chart.options.plugins.tooltip.backgroundColor,
                chart.options.scales.y.ticks.color];
    })()"""
    before = page.evaluate(read)
    assert all(colour.startswith("rgb(") for colour in before)
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    until(page, f"{read}[1] !== {json.dumps(before[1])}")
    after = page.evaluate(read)
    assert after[0] != before[0]
    assert after[2] != before[2]


@pytest.mark.browser
def test_colours_follow_the_system_too(open_page):
    page = open_page("/gallery/chart", theme="system")
    page.emulate_media(color_scheme="light")
    until(page, CHARTS_READY)
    read = """Chart.getChart(document.querySelector('[data-chart-examples] canvas'))
        .options.plugins.tooltip.backgroundColor"""
    before = page.evaluate(read)
    page.emulate_media(color_scheme="dark")
    until(page, f"{read} !== {json.dumps(before)}")


@pytest.mark.browser
def test_a_series_hidden_in_the_legend_stays_hidden_after_a_change_of_theme(open_page):
    page = open_page("/gallery/chart", theme="system")
    page.emulate_media(color_scheme="light")
    until(page, CHARTS_READY)
    chart = "Chart.getChart(document.querySelector('[data-chart-examples] canvas'))"
    page.evaluate(f"{chart}.hide(1)")
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    until(page, f"{chart}.options.plugins.tooltip.backgroundColor !== 'rgb(255, 255, 255)'")
    assert page.evaluate(f"{chart}.isDatasetVisible(1)") is False


@pytest.mark.browser
def test_motion_is_off_when_a_person_asks(open_page):
    page = open_page("/gallery/chart")
    page.emulate_media(reduced_motion="reduce")
    page.reload()
    until(page, CHARTS_READY)
    chart = "Chart.getChart(document.querySelector('[data-chart-examples] canvas'))"
    assert page.evaluate(f"{chart}.options.animation") is False


@pytest.mark.browser
def test_a_chart_is_redrawn_by_a_screen_size_change(open_page):
    page = open_page("/gallery/chart", width=1280)
    until(page, CHARTS_READY)
    canvas = page.locator("[data-chart-examples] canvas").first
    wide = canvas.bounding_box()["width"]
    page.set_viewport_size({"width": 390, "height": 800})
    page.wait_for_timeout(300)
    box = canvas.bounding_box()
    assert box["width"] < wide
    assert not overflows_sideways(page)
