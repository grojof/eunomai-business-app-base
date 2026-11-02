"""Boards on their own, and what they need from the shell: what stays in an application after the demo is deleted."""

import json
import re
from datetime import UTC, datetime

import pytest

from app.core.boards import RANK_STEP, Board, BoardCard, BoardColumn, rank_between, read_move, renumbered
from app.core.forms import Refused
from app.core.templating import environment
from tests.helpers import ROOT
from tools import vendor

MACROS = environment.get_template("ui/macros.html").module
COLUMNS = ("todo", "doing", "done")


def board(can_move=True, focus=None):
    columns = [
        BoardColumn("todo", "To do", [BoardCard(7, 3, "Card seven"), BoardCard(9, 1, "Card nine")], 5, "/list?s=todo"),
        BoardColumn("doing", "Doing", [], 0),
        BoardColumn("done", "Done", [BoardCard(4, 2, "Card four")], 1),
    ]
    return Board("things", "Things", columns, "/things/move", can_move, focus=focus, hidden={"place": "roof"})


def drawn(**options):
    return str(MACROS.board(board(**options), caller=lambda card: f"<p>{card.label}</p>"))


def test_a_board_is_columns_with_headings_and_lists():
    html = drawn()
    assert html.count("<section") == 3
    assert html.count("<ol") == 3
    assert 'aria-labelledby="things-todo-title"' in html
    assert '<h2 id="things-doing-title"' in html


def test_each_card_carries_a_plain_form_that_moves_it():
    html = drawn()
    assert html.count('method="post" action="/things/move"') == 3
    assert '<input type="hidden" name="card" value="7">' in html
    assert '<input type="hidden" name="version" value="3">' in html
    assert '<input type="hidden" name="place" value="roof">' in html
    assert '<label class="block text-xs font-medium" for="things-move-7">' in html
    assert "Card seven" in html.split('for="things-move-7"')[1].split("</label>")[0]


def test_a_person_who_may_not_move_gets_no_form_and_no_dragging():
    html = drawn(can_move=False)
    assert "<form" not in html
    assert "data-can-move" not in html
    assert "cursor-grab" not in html


def test_an_empty_column_says_so_and_a_long_one_leads_to_the_rest():
    html = drawn()
    assert "data-board-empty" in html
    assert 'href="/list?s=todo"' in html
    assert "3 more in the list" in html


def test_focus_comes_back_to_the_card_that_moved():
    assert '<select id="things-move-9" class="select select-xs w-full" name="to" data-focus>' in drawn(focus=9)


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize(
    ("card", "to", "after", "version"),
    [
        ("x", "todo", "", "1"),
        ("7", "nowhere", "", "1"),
        ("7", "todo", "1 OR 1=1", "1"),
        ("7", "todo", "", "-1"),
        ("9" * 20, "todo", "", "1"),
        ("7", "todo", "", chr(0x0661)),  # a digit, but not one of 0 to 9
    ],
)
def test_a_move_is_read_against_its_lists(card, to, after, version):
    with pytest.raises(Refused):
        read_move(card, to, after, version, COLUMNS)


def test_a_move_reads_what_it_may_be():
    move = read_move("7", "doing", "4", "3", COLUMNS)
    assert (move.card, move.to, move.after, move.version) == (7, "doing", 4, 3)
    assert read_move("7", "doing", "", "", COLUMNS).after is None


def test_a_card_lands_half_way_between_its_neighbours():
    assert rank_between(None, None) == RANK_STEP
    assert rank_between(None, 2048) == 1024
    assert rank_between(2048, None) == 2048 + RANK_STEP
    assert rank_between(1024, 2048) == 1536
    assert rank_between(1024, 1025) is None
    assert rank_between(5, 5) is None


def test_a_column_numbered_again_has_its_gaps_back():
    assert renumbered([9, 4, 7]) == [{"id": 9, "rank": 1024}, {"id": 4, "rank": 2048}, {"id": 7, "rank": 3072}]


@pytest.mark.rule("SEC-06")
def test_htmx_never_settles_a_style_attribute():
    """htmx copies the attributes it settles with setAttribute, and a style attribute set that way is inline style,
    which the policy refuses: a dragged card, which SortableJS moves through the CSSOM, would break it."""
    layout = (ROOT / "app" / "ui" / "templates" / "layout.html").read_text(encoding="utf-8")
    config = json.loads(re.search(r'<meta name="htmx-config" content=\'(.*?)\'>', layout)[1])
    assert config["attributesToSettle"] == ["class", "width", "height"]


def test_the_board_library_is_the_version_vendor_json_says():
    entry = vendor.read_entries()["sortablejs"]
    assert entry["on_demand"] is True
    assert f"Sortable {entry['version']}" in (ROOT / entry["target"]).read_text(encoding="utf-8")[:100]


def test_the_board_library_is_past_the_two_week_rule():
    """The rule has no exceptions but a vulnerability fix. It asks the registry, so it needs a network."""
    version = vendor.read_entries()["sortablejs"]["version"]
    try:
        published = vendor.read_json("https://registry.npmjs.org/sortablejs")["time"][version]
    except OSError:
        pytest.skip("the registry cannot be reached")
    assert datetime.now(UTC) - datetime.fromisoformat(published) >= vendor.WINDOW


def test_a_page_without_a_board_does_not_load_the_library(client, person):
    assert "Sortable" not in client.get("/settings", headers=person).text
