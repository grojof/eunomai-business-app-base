"""The board: work orders by state, moved by a form, by keyboard, without JavaScript and by dragging."""

import re
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.core.i18n import PSEUDO
from app.demo.board import column_lock
from app.demo.models import WorkOrder
from app.main import create_app
from tests.conftest import PERSON, TEST_DATABASE_URL, build_settings, empty_database, page_opener, running_server
from tests.demo.support import announced, fill, until
from tests.helpers import overflows_sideways, run_axe, untranslated

SAME_SITE = {"Sec-Fetch-Site": "same-origin"}
HTMX = {"HX-Request": "true"}
ALLOWED = ("Business App", "Demo Person", "Air compressor", "Conveyor belt", "Standby generator", "Cooling tower")
ALLOWED += ("Forklift", "Jan ", "Feb ", "Mar ", "Apr ", "May ", "Jun ", "Jul ", "Aug ", "Sep ", "Oct ", "Nov ", "Dec ")
ALLOWED += ("Preventive plan", "Safety checks", "Oil change", "Filter replacement", "Belt replacement")
ALLOWED += ("Calibration", "Leak repair", "Electrical inspection")
READY = "document.documentElement.dataset.boardReady !== undefined"


def orders(url, status):
    engine = create_database_engine(url)
    with Session(engine) as session:
        found = session.scalars(
            select(WorkOrder).where(WorkOrder.status == status).order_by(WorkOrder.rank, WorkOrder.id)
        ).all()
    engine.dispose()
    return found


def read(url, number):
    engine = create_database_engine(url)
    with Session(engine) as session:
        order = session.get(WorkOrder, number)
    engine.dispose()
    return order


@pytest.fixture
def writable(database_url):
    fill(database_url, 500)
    client = TestClient(create_app(build_settings(database_url=database_url)), raise_server_exceptions=False)
    client.headers.update(PERSON | SAME_SITE)
    return client, database_url


def moving(order, to, after="", **more):
    return {"card": str(order.id), "to": to, "after": after, "version": str(order.version), **more}


def test_the_board_has_a_column_for_each_state(filled):
    html = filled.get("/board").text
    assert html.count("data-board-list") == 5
    assert html.count('method="post" action="/board/move"') >= 5
    assert "data-can-move" in html


def test_a_location_narrows_the_board(filled):
    html = filled.get("/board?location=Roof").text
    assert '<option value="Roof" selected>' in html
    assert '<input type="hidden" name="location" value="Roof">' in html


@pytest.mark.rule("SEC-02")
def test_moving_needs_its_role(filled_url):
    client = TestClient(create_app(build_settings(database_url=filled_url)))
    staff = PERSON | {"X-Remote-Groups": "staff"} | SAME_SITE
    html = client.get("/board", headers=staff).text
    assert 'action="/board/move"' not in html
    assert "data-can-move" not in html
    assert client.post("/board/move", data={"card": "1", "to": "planned"}, headers=staff).status_code == 403


@pytest.mark.rule("SEC-07")
def test_a_move_from_another_site_is_refused(writable):
    client, url = writable
    order = orders(url, "reported")[0]
    response = client.post("/board/move", data=moving(order, "planned"), headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert read(url, order.id).status == "reported"


def test_a_move_without_javascript_puts_the_card_first_and_says_so(writable):
    client, url = writable
    order = orders(url, "reported")[-1]
    response = client.post("/board/move", data=moving(order, "planned", location="Roof"), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/board?location=Roof&moved={order.id}"
    assert orders(url, "planned")[0].id == order.id
    assert read(url, order.id).version == order.version + 1
    assert f"Work order {order.id} is now in Planned." in client.get(response.headers["location"]).text


def test_a_card_lands_after_the_one_it_was_dropped_after(writable):
    client, url = writable
    planned = orders(url, "planned")
    order = orders(url, "reported")[0]
    client.post("/board/move", data=moving(order, "planned", str(planned[1].id)))
    assert [row.id for row in orders(url, "planned")][:4] == [planned[0].id, planned[1].id, order.id, planned[2].id]


def test_a_move_within_a_column_reorders_it(writable):
    client, url = writable
    column = orders(url, "planned")
    client.post("/board/move", data=moving(column[0], "planned", str(column[2].id)))
    assert [row.id for row in orders(url, "planned")][:3] == [column[1].id, column[2].id, column[0].id]


def test_with_no_room_left_the_column_is_numbered_again_and_no_other_version_moves(writable):
    client, url = writable
    engine = create_database_engine(url)
    with engine.begin() as connection:
        for position, row in enumerate(orders(url, "planned")):
            connection.execute(update(WorkOrder.__table__).where(WorkOrder.id == row.id).values(rank=position))
    engine.dispose()
    column = orders(url, "planned")
    order = orders(url, "reported")[0]
    client.post("/board/move", data=moving(order, "planned", str(column[0].id)))
    after = orders(url, "planned")
    assert [row.id for row in after][:3] == [column[0].id, order.id, column[1].id]
    assert len({row.rank for row in after}) == len(after)
    versions = {row.id: row.version for row in column}
    assert all(row.version == versions[row.id] for row in after if row.id != order.id)


@pytest.mark.rule("A11Y-09")
def test_htmx_gets_the_board_with_focus_on_the_card_and_the_move_announced(writable):
    client, url = writable
    order = orders(url, "reported")[0]
    html = client.post("/board/move", data=moving(order, "in_progress"), headers=HTMX).text
    assert "<html" not in html
    assert f'<summary id="board-move-{order.id}" class="btn btn-ghost btn-xs" data-focus>' in html
    assert f'data-announce="Work order {order.id} is now in In progress."' in html


def test_someone_who_moved_it_first_is_a_conflict_that_moves_nothing(writable):
    client, url = writable
    order = orders(url, "reported")[0]
    client.post("/board/move", data=moving(order, "checked"))
    response = client.post("/board/move", data=moving(order, "planned"))
    assert response.status_code == 409
    assert "Someone else moved this work order first" in response.text
    assert read(url, order.id).status == "checked"
    assert client.post("/board/move", data=moving(order, "planned"), headers=HTMX).status_code == 200


def test_a_card_to_follow_that_is_elsewhere_is_refused(writable):
    client, url = writable
    order = orders(url, "reported")[0]
    elsewhere = orders(url, "closed")[0]
    response = client.post("/board/move", data=moving(order, "planned", str(elsewhere.id)))
    assert response.status_code == 409
    assert "That place on the board has changed" in response.text
    assert read(url, order.id).status == "reported"


@pytest.mark.rule("SEC-03")
@pytest.mark.parametrize(
    "form",
    [{"card": "1", "to": "elsewhere"}, {"card": "x", "to": "planned"}, {"card": "1", "to": "planned", "after": "-2"}],
)
def test_a_move_that_is_not_one_is_refused(writable, form):
    client, _url = writable
    assert client.post("/board/move", data=form).status_code == 400


def test_a_card_that_is_gone_is_not_found(writable):
    client, _url = writable
    assert client.post("/board/move", data={"card": "999999", "to": "planned", "version": "1"}).status_code == 404


@pytest.mark.rule("LANG-01")
@pytest.mark.parametrize("path", ["/board", "/board?location=Roof"])
def test_no_text_outside_translation(filled, path):
    filled.cookies.set("language", PSEUDO)
    assert untranslated(filled.get(path).text, ALLOWED) == []


@pytest.mark.rule("LANG-01")
def test_no_text_outside_translation_without_the_rows(client, person):
    client.cookies.set("language", PSEUDO)
    assert untranslated(client.get("/board", headers=person).text, ALLOWED) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-01")
@pytest.mark.rule("A11Y-05")
@pytest.mark.rule("A11Y-06")
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 375])
def test_the_board_passes_the_scan(open_filled, theme, width):
    assert run_axe(open_filled("/board?location=Roof", theme=theme, width=width, bypass_csp=True)) == []


@pytest.mark.browser
@pytest.mark.rule("A11Y-12")
@pytest.mark.rule("LANG-11")
def test_the_board_fits_a_phone_with_longer_texts(open_filled):
    assert not overflows_sideways(open_filled("/board", language=PSEUDO, width=320))


@pytest.fixture
def own_board(browser, tmp_path):
    url = f"sqlite:///{(tmp_path / 'board.db').as_posix()}"
    fill(url, 500)
    settings = build_settings(database_url=url, fake_identity=True, fake_groups=["admins"], trusted_proxies=[])
    with running_server(create_app(settings)) as port, page_opener(browser, f"http://127.0.0.1:{port}") as opener:
        yield opener, url


def card(page, column, position=0):
    return page.locator(f"[data-column={column}] [data-card]").nth(position)


@pytest.mark.browser
@pytest.mark.rule("A11Y-09")
def test_the_keyboard_moves_a_card_and_focus_follows_it(own_board):
    opener, url = own_board
    page = opener("/board")
    page.evaluate("window.notReloaded = true")
    number = card(page, "reported").get_attribute("data-card")
    page.locator(f"#board-move-{number}").focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == f"board-move-{number}-to"
    page.locator(f"#board-move-{number}-to").select_option("in_progress")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    announced(page, f"Work order {number} is now in In progress.")
    until(page, f"document.activeElement.id === 'board-move-{number}'")
    assert card(page, "in_progress").get_attribute("data-card") == number
    assert page.evaluate("window.notReloaded")
    assert read(url, int(number)).status == "in_progress"


def drag(page, source, target):
    """A pointer's drag, in small steps, as a person makes it, from the card's text, which is no link, to the lower
    part of the target card."""
    start = source.locator("p").first.bounding_box()
    end = target.bounding_box()
    x, y = start["x"] + start["width"] / 2, start["y"] + start["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    to_x, to_y = end["x"] + end["width"] / 2, end["y"] + end["height"] * 0.8
    for step in range(1, 16):
        page.mouse.move(x + (to_x - x) * step / 15, y + (to_y - y) * step / 15)
        page.wait_for_timeout(20)
    page.mouse.up()


@pytest.mark.browser
@pytest.mark.rule("SEC-06")
def test_a_card_dragged_to_another_column_is_saved_where_it_landed(own_board):
    opener, url = own_board
    page = opener("/board")
    problems = []
    page.on("console", lambda message: problems.append(message.text) if message.type == "error" else None)
    until(page, READY)
    number = card(page, "reported").get_attribute("data-card")
    first = card(page, "planned").get_attribute("data-card")
    drag(page, card(page, "reported"), card(page, "planned"))
    announced(page, f"Work order {number} is now in Planned.")
    assert [row.id for row in orders(url, "planned")][:2] == [int(first), int(number)]
    assert problems == []
    second = card(page, "reported").get_attribute("data-card")
    drag(page, card(page, "reported"), card(page, "checked"))
    announced(page, f"Work order {second} is now in Checked.")
    assert read(url, int(second)).status == "checked"


@pytest.mark.browser
def test_a_finger_can_drag_a_card_too(own_board):
    opener, url = own_board
    page = opener("/board")
    until(page, READY)
    number = card(page, "reported").get_attribute("data-card")
    start = card(page, "reported").locator("p").first.bounding_box()
    end = card(page, "planned").bounding_box()
    session = page.context.new_cdp_session(page)

    def touch(kind, x, y):
        points = [] if kind == "touchEnd" else [{"x": x, "y": y}]
        session.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    x, y = start["x"] + start["width"] / 2, start["y"] + start["height"] / 2
    to_x, to_y = end["x"] + end["width"] / 2, end["y"] + end["height"] * 0.8
    touch("touchStart", x, y)
    page.wait_for_timeout(400)  # a finger that rests before it moves: a quick swipe scrolls the page instead
    for step in range(1, 21):
        touch("touchMove", x + (to_x - x) * step / 20, y + (to_y - y) * step / 20)
        page.wait_for_timeout(30)
    touch("touchEnd", 0, 0)
    announced(page, f"Work order {number} is now in Planned.")
    assert read(url, int(number)).status == "planned"


@pytest.mark.browser
def test_without_javascript_the_form_moves_a_card(own_board):
    opener, url = own_board
    page = opener("/board?location=Roof", javascript=False)
    number = card(page, "reported").get_attribute("data-card")
    page.locator(f"#board-move-{number}").click()
    page.locator(f"#board-move-{number}-to").select_option("closed")
    page.locator(f"[data-card='{number}']").get_by_role("button", name="Move").click()
    page.wait_for_url(re.compile(rf"location=Roof&moved={number}"))
    assert f"Work order {number} is now in Closed." in page.locator("main").inner_text()
    assert read(url, int(number)).status == "closed"


def test_a_rank_is_a_big_integer_on_both_databases():
    assert isinstance(WorkOrder.__table__.c.rank.type, BigInteger)


def test_a_move_locks_the_columns_it_reads_where_the_database_can():
    statement = column_lock(("planned", "reported"))
    assert "FOR UPDATE" in str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" not in str(statement.compile(dialect=sqlite.dialect()))


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="row locks need PostgreSQL: set TEST_DATABASE_URL")
def test_a_move_waits_for_a_renumbering_and_lands_where_it_was_asked(tmp_path):
    """One session holds the column while it numbers it again; a move into it waits, then reads the new numbers."""
    with empty_database("postgresql", tmp_path) as url:
        fill(url, 500)
        client = TestClient(create_app(build_settings(database_url=url)))
        client.headers.update(PERSON | SAME_SITE)
        column = orders(url, "planned")
        moving_card = orders(url, "reported")[0]
        engine = create_database_engine(url)
        with Session(engine) as holder:
            holder.execute(column_lock(("planned", "reported")))
            result = {}
            worker = threading.Thread(
                target=lambda: result.update(
                    status=client.post(
                        "/board/move", data=moving(moving_card, "planned", str(column[1].id))
                    ).status_code
                )
            )
            worker.start()
            worker.join(timeout=1)
            assert worker.is_alive(), "the move should wait for the column"
            for position, row in enumerate(column):
                holder.execute(
                    update(WorkOrder.__table__).where(WorkOrder.id == row.id).values(rank=(position + 1) * 7)
                )
            holder.commit()
        worker.join(timeout=30)
        engine.dispose()
        assert result["status"] == 200
        assert [row.id for row in orders(url, "planned")][:3] == [column[0].id, column[1].id, moving_card.id]
