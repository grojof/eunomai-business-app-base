"""The macros of the data milestone on their own: what stays in an application after the demo is deleted."""

import pytest
from markupsafe import escape

from app.core.tables import Column, ListView
from app.core.templating import environment

MACROS = environment.get_template("ui/macros.html").module


def view_of(**params: str) -> ListView:
    columns = (Column("name", "Name", "name"), Column("cost", "Cost", "cost", numeric=True, first="desc"))
    view = ListView.read("things", "/things", params, columns, None, "name")
    view.rows, view.total = [{"name": "One"}], 120
    return view


def test_breadcrumbs_mark_where_a_person_is():
    html = str(MACROS.breadcrumbs([("Equipment", "/equipment"), ("A-1", "")]))
    assert '<a href="/equipment">Equipment</a>' in html
    assert '<span aria-current="page">A-1</span>' in html


def test_a_description_list_is_a_real_one():
    html = str(MACROS.description_list([("Code", "<b>")]))
    assert "<dl" in html
    assert "<dt" in html
    assert "<dd" in html
    assert escape("<b>") in html


def test_a_status_label_always_has_its_word():
    html = str(MACROS.status_label("Stopped", "danger"))
    assert "status-error" in html
    assert "Stopped" in html
    assert 'aria-hidden="true"' in html


def test_a_status_label_refuses_a_kind_it_does_not_have():
    with pytest.raises(Exception, match="invented"):
        MACROS.status_label("Stopped", "invented")


def test_tabs_are_links_in_a_navigation():
    html = str(MACROS.tabs("Sections", [("a", "One", "/one"), ("b", "Two", "/two")], "b"))
    assert '<nav aria-label="Sections"' in html
    assert 'role="tab' not in html
    assert html.count("aria-current") == 1
    assert "hx-get" not in html


def test_a_sorted_header_says_so_and_the_others_do_not():
    html = str(MACROS.server_table(view_of(sort="cost"), "Things", caller=lambda row: row["name"]))
    assert html.count("aria-sort") == 1
    assert 'aria-sort="descending"' in html
    assert 'href="/things?sort=cost&amp;dir=asc"' in html


def test_the_table_box_can_be_reached_by_keyboard_and_is_named():
    html = str(MACROS.server_table(view_of(), "Things", caller=lambda row: row["name"]))
    assert 'role="region" tabindex="0" aria-labelledby="things-caption"' in html
    assert '<caption id="things-caption"' in html
    assert "table-pin-rows" in html


def test_pagination_marks_the_page_and_names_its_arrows():
    html = str(MACROS.pagination(view_of(page="3")))
    assert 'aria-current="page"' in html
    assert 'rel="prev"' in html
    assert 'rel="next"' in html
    assert 'href="/things?page=4"' in html


def test_the_first_page_has_no_previous_link():
    html = str(MACROS.pagination(view_of()))
    assert 'rel="prev"' not in html
    assert 'aria-disabled="true"' in html


def test_a_filter_bar_is_a_get_form_with_labels_that_works_alone():
    view = view_of(sort="cost")
    html = str(MACROS.filter_bar(view))
    assert 'method="get" action="/things"' in html
    assert '<input type="hidden" name="sort" value="cost">' in html
    assert 'for="things-search"' in html
    assert "noscript:inline-flex" in html


def test_an_empty_state_can_carry_an_action():
    html = str(MACROS.empty_state("Nothing", "Try again", caller=lambda: "ACTION"))
    assert "ACTION" in html


def test_a_list_offers_its_own_choices_as_forms_that_say_their_state():
    view = view_of()
    view.offered, view.dense = ("list_width", "list_density"), True
    html = str(MACROS.list_summary(view, "120 things"))
    assert html.count('action="/preferences"') == 2
    assert 'name="layout_list_width" value="wide" aria-pressed="false"' in html
    assert 'name="layout_list_density" value="normal" aria-pressed="true"' in html
    assert '<input type="hidden" name="next" value="/things">' in html
    assert 'hx-post="/preferences" hx-target="#things-results"' in html


def test_a_list_offers_nothing_an_application_fixed():
    html = str(MACROS.list_summary(view_of(), "120 things"))
    assert "/preferences" not in html
    assert "data-list-wide" not in html


def test_dense_rows_are_smaller_and_bring_wide_columns_sooner():
    view = view_of()
    columns = (Column("name", "Name", "name"), Column("cost", "Cost", "cost", wide_only=True))
    view.columns, view.dense = columns, True
    html = str(MACROS.server_table(view, "Things", caller=lambda row: MACROS.cell(row["name"], wide_only=True)))
    assert "table-xs table-dense" in html
    assert "table-sm" not in html
    assert html.count("wide-only hidden md:table-cell") == 2


def test_a_wide_list_marks_itself_for_the_page():
    view = view_of()
    view.wide = True
    assert "data-list-wide" in str(MACROS.list_summary(view, "120 things"))


def test_a_heading_stays_in_the_page_unless_the_top_bar_asked_for_it():
    html = str(MACROS.page_heading("Things", "All of them"))
    assert "<h1>Things</h1>" in html
