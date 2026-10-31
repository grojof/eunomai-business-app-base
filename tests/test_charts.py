"""The chart macro and its data: what stays in an application after the demo is deleted."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.charts import CHART_TYPES, Point, Series, chart_data, point_data
from app.core.templating import environment
from tests.helpers import ROOT
from tools import vendor

MACROS = environment.get_template("ui/macros.html").module
DATA = chart_data(["Jan", "Feb"], [Series("Hours", [Decimal("1250.5"), 7])], "Month", places=1)


def rendered(data=DATA, kind="bar"):
    return str(MACROS.chart("Hours", "Hours rose in February.", data, kind, "chart-hours"))


def config_of(html):
    return json.loads(re.search(r'<script type="application/json">(.*?)</script>', html, re.S)[1])


@pytest.mark.rule("A11Y-10")
def test_a_chart_always_has_its_summary_and_its_data_as_a_table():
    html = rendered()
    assert "<figure" in html
    assert "<figcaption" in html
    assert "Hours rose in February." in html
    assert "<table" in html
    assert "1,250.5" in html


@pytest.mark.rule("A11Y-10")
def test_the_canvas_is_named_and_points_at_its_summary():
    html = rendered()
    assert 'role="img" aria-label="Hours" aria-describedby="chart-hours-summary"' in html
    assert 'id="chart-hours-summary"' in html


@pytest.mark.rule("A11Y-10")
def test_every_kind_of_chart_brings_the_table():
    for kind in sorted(CHART_TYPES):
        assert "<table" in rendered(kind=kind)


def test_numbers_travel_as_text_so_none_becomes_a_float_here():
    value = Decimal("0.12345678901234567890")
    config = chart_data(["A"], [Series("S", [value])], "L").config_for("bar")
    assert config["series"][0]["values"] == ["0.12345678901234567890"]


def test_an_empty_value_stays_empty():
    data = chart_data(["A", "B"], [Series("S", [1, None])], "L")
    assert data.config["series"][0]["values"] == ["1", None]
    assert data.rows[1] == ["B", ""]


def test_the_configuration_travels_as_data_and_is_escaped():
    data = chart_data(["</script><b>"], [Series("S", [1])], "L")
    html = rendered(data)
    assert "</script><b>" not in html
    assert config_of(html)["labels"] == ["</script><b>"]


def test_a_type_chart_js_does_not_have_is_refused():
    with pytest.raises(ValueError, match="Not a chart type"):
        rendered(kind="sparkline")


def test_series_keep_a_fixed_order_of_colours():
    data = chart_data(["A"], [Series(name, [1]) for name in "abcd"], "L")
    assert [line["colour"] for line in data.config["series"]] == ["primary", "accent", "secondary", "info"]


def test_a_fifth_series_is_refused_rather_than_given_a_made_up_colour():
    with pytest.raises(ValueError, match="four series"):
        chart_data(["A"], [Series(name, [1]) for name in "abcde"], "L")


def test_a_series_must_match_its_labels():
    with pytest.raises(ValueError, match="one value per label"):
        chart_data(["A", "B"], [Series("S", [1])], "L")


def test_points_have_their_own_table():
    data = point_data([("All", [Point("A-1", 1, 2, 3)])], "Code", "Age", "Cost", "Orders")
    assert data.headers == ["Code", "Age", "Cost", "Orders"]
    assert data.rows == [["A-1", "1", "2", "3"]]
    assert data.config["series"][0]["values"] == [{"x": "1", "y": "2", "r": "3", "label": "A-1"}]


def test_the_library_is_loaded_with_its_integrity_only_where_a_chart_is():
    html = rendered()
    assert 'data-chart-library="/static/ui/vendor/chart.umd.min.js"' in html
    assert re.search(r'data-chart-integrity="sha384-[\w+/=]+"', html)
    layout = (ROOT / "app" / "ui" / "templates" / "layout.html").read_text(encoding="utf-8")
    assert "chart.umd" not in layout


def test_a_page_without_a_chart_does_not_load_the_library(client, person):
    assert "chart.umd" not in client.get("/settings", headers=person).text


def test_the_script_has_no_colour_of_its_own():
    script = (ROOT / "app" / "ui" / "static" / "charts.js").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", script)
    assert "oklch" not in script.replace("use oklch", "")


def test_the_library_in_the_repository_is_the_version_vendor_json_says():
    entry = vendor.read_entries()["chart.js"]
    assert f"Chart.js v{entry['version']}" in (ROOT / entry["target"]).read_text(encoding="utf-8")[:200]


@pytest.mark.parametrize("name", ["chart.js", "htmx.org"])
def test_the_copied_files_are_past_the_two_week_rule(name):
    """The rule has no exceptions but a vulnerability fix. It asks the registry, so it needs a network."""
    version = vendor.read_entries()[name]["version"]
    try:
        published = vendor.read_json(f"https://registry.npmjs.org/{name}")["time"][version]
    except OSError:
        pytest.skip("the registry cannot be reached")
    assert datetime.now(UTC) - datetime.fromisoformat(published) >= vendor.WINDOW
