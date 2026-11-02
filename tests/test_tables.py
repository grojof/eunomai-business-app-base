"""The list layer on its own, with a table of its own: what stays in an application after the demo is deleted."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Column as SqlColumn
from sqlalchemy import Date, Integer, MetaData, String, Table, func, insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.columns import ExactDecimal
from app.core.database import create_database_engine
from app.core.tables import Column, Filter, ListView, list_query

METADATA = MetaData()
THING = Table(
    "thing",
    METADATA,
    SqlColumn("id", Integer, primary_key=True),
    SqlColumn("name", String(40)),
    SqlColumn("kind", String(10)),
    SqlColumn("cost", ExactDecimal()),
    SqlColumn("due", Date, nullable=True),
)
ROWS = [
    {"id": 1, "name": "9 volts", "kind": "a", "cost": Decimal("9"), "due": date(2027, 1, 1)},
    {"id": 2, "name": "100% cotton", "kind": "a", "cost": Decimal("100"), "due": None},
    {"id": 3, "name": "50_50 mix", "kind": "b", "cost": Decimal("20.5"), "due": date(2026, 1, 1)},
    {"id": 4, "name": "Sample", "kind": "b", "cost": Decimal("20.5"), "due": date(2028, 1, 1)},
]
ATTACKS = [
    "name; DROP TABLE thing; --",
    "name) UNION SELECT * FROM sqlite_master --",
    "1 OR 1=1",
    "(SELECT 1)",
    "' OR '1'='1",
    '" OR ""="',
    "%' OR 1=1 --",
    "name\x00",
    "-1",
    "9" * 5000,
]


def view_of(params: dict[str, str]) -> ListView:
    return ListView.read(
        "things",
        "/things",
        params,
        (
            Column("name", "Name", THING.c.name),
            Column("cost", "Cost", THING.c.cost, numeric=True, first="desc"),
            Column("due", "Due", THING.c.due, nullable=True),
            Column("note", "Note"),
        ),
        THING.c.id,
        "name",
        (Filter("kind", "Kind", [("a", "A"), ("b", "B")], lambda value: THING.c.kind == value, every="Every kind"),),
        (THING.c.name,),
        "Name",
    )


@pytest.fixture
def session(database_url: str) -> Iterator[Session]:
    engine = create_database_engine(database_url)
    METADATA.create_all(engine)
    with Session(engine) as session:
        session.execute(insert(THING), ROWS)
        session.commit()
        yield session
    METADATA.drop_all(engine)
    engine.dispose()


def loaded(session: Session, **params: str) -> ListView:
    view = view_of(params)
    view.load(session, select(THING.c.id))
    return view


def names(view: ListView) -> list[int]:
    return view.rows


@pytest.mark.rule("SEC-05")
@pytest.mark.parametrize("attack", ATTACKS)
@pytest.mark.parametrize("field", ["sort", "dir", "page", "size", "kind"])
def test_nothing_outside_the_lists_reaches_the_query(session, field, attack):
    view = loaded(session, **{field: attack})
    assert view.sort == "name"
    assert view.direction == "asc"
    assert view.size == 25
    assert view.page == 1
    assert view.chosen["kind"] == ""
    assert view.total == len(ROWS)
    assert session.scalar(select(func.count()).select_from(THING)) == len(ROWS)


@pytest.mark.rule("SEC-05")
@pytest.mark.parametrize("attack", [text for text in ATTACKS if "\x00" not in text and len(text) < 80])
def test_a_search_travels_as_a_parameter(session, attack):
    view = loaded(session, q=attack)
    assert view.total == 0
    compiled = select(THING.c.id).where(*view.conditions).order_by(*view.order()).compile(dialect=postgresql.dialect())
    assert attack not in str(compiled)
    escaped = attack.replace("/", "//").replace("%", "/%").replace("_", "/_")
    assert any(escaped in str(value) for value in compiled.params.values())
    assert session.scalar(select(func.count()).select_from(THING)) == len(ROWS)


@pytest.mark.rule("SEC-05")
def test_a_column_that_does_not_sort_cannot_be_asked_to(session):
    assert loaded(session, sort="note").sort == "name"


def test_a_nul_in_a_search_is_dropped(session):
    assert loaded(session, q="Sam\x00ple").rows == [4]


def test_a_search_is_cut_to_its_limit():
    assert len(view_of({"q": "x" * 500}).term) == 80


def test_percent_and_underscore_are_only_characters(session):
    assert loaded(session, q="%").rows == [2]
    assert loaded(session, q="_").rows == [3]


def test_a_search_ignores_capitals_on_both_databases(session):
    assert loaded(session, q="SAMPLE").rows == [4]


@pytest.mark.rule("DATA-03")
def test_sorting_by_a_decimal_is_numeric_on_both_databases(session):
    assert loaded(session, sort="cost", dir="asc").rows == [1, 3, 4, 2]
    assert loaded(session, sort="cost", dir="desc").rows == [2, 4, 3, 1]


def test_equal_values_keep_a_fixed_order(session):
    assert loaded(session, sort="cost", dir="asc", size="10").rows[1:3] == [3, 4]


def test_rows_without_a_value_go_last_either_way_on_both_databases(session):
    assert loaded(session, sort="due", dir="asc").rows == [3, 1, 4, 2]
    assert loaded(session, sort="due", dir="desc").rows == [4, 1, 3, 2]


def test_a_filter_narrows_and_counts(session):
    view = loaded(session, kind="b")
    assert (view.rows, view.total) == ([3, 4], 2)


def test_a_page_past_the_end_shows_the_last_one(session):
    view = loaded(session, size="10", page="99")
    assert (view.page, view.pages) == (1, 1)
    assert view.rows


def test_no_rows_is_a_state_and_not_an_error(session):
    view = loaded(session, q="nothing like this")
    assert (view.rows, view.total, view.pages, view.first_row, view.last_row) == ([], 0, 0, 0, 0)


@pytest.mark.parametrize(
    ("page", "pages", "expected"),
    [
        (1, 1, [1]),
        (1, 3, [1, 2, 3]),
        (1, 2000, [1, 2, None, 2000]),
        (5, 2000, [1, None, 4, 5, 6, None, 2000]),
        (3, 2000, [1, 2, 3, 4, None, 2000]),
        (2000, 2000, [1, None, 1999, 2000]),
        (4, 7, [1, 2, 3, 4, 5, 6, 7]),
    ],
)
def test_the_pages_on_offer(page, pages, expected):
    view = view_of({"page": str(page), "size": "10"})
    view.total = pages * 10
    assert view.page_numbers() == expected


@pytest.mark.rule("USE-05")
def test_an_address_holds_the_whole_state_and_reads_back_the_same():
    view = view_of({"q": "a b&c", "kind": "b", "sort": "cost", "dir": "asc", "size": "50", "page": "3"})
    query = dict(part.split("=") for part in view.here.split("?")[1].split("&"))
    assert query == {"q": "a+b%26c", "kind": "b", "sort": "cost", "dir": "asc", "size": "50", "page": "3"}


@pytest.mark.rule("USE-05")
def test_the_default_state_has_a_clean_address():
    assert view_of({}).here == "/things"
    assert view_of({"sort": "name", "dir": "asc", "page": "1", "size": "25", "q": "", "kind": ""}).here == "/things"


@pytest.mark.rule("USE-05")
def test_a_change_goes_back_to_the_first_page_and_keeps_the_rest():
    view = view_of({"kind": "a", "page": "4", "size": "10"})
    assert view.link(sort="cost", dir="desc") == "/things?kind=a&sort=cost&size=10"
    assert view.link(page=5) == "/things?kind=a&size=10&page=5"


def test_a_sort_link_starts_where_the_column_says_and_then_turns_around():
    view = view_of({})
    name, cost, *_rest = view.columns
    assert view.sort_link(cost) == "/things?sort=cost"
    assert view.sort_link(name) == "/things?dir=desc"
    assert view_of({"sort": "cost"}).sort_link(cost) == "/things?sort=cost&dir=asc"


def test_only_the_sorted_column_has_a_sort_state():
    view = view_of({"sort": "cost", "dir": "asc"})
    assert [view.sort_state(column) for column in view.columns] == ["", "ascending", "", ""]


def test_what_narrows_a_list_can_each_be_removed():
    view = view_of({"q": "x", "kind": "a", "sort": "cost"})
    assert view.active == [("Name", "x", "/things?kind=a&sort=cost"), ("Kind", "A", "/things?q=x&sort=cost")]
    assert view.clear_link == "/things?sort=cost"


def test_the_same_list_elsewhere_keeps_its_filters_and_order_but_not_its_page():
    assert view_of({"kind": "a", "sort": "cost", "page": "3"}).elsewhere("/things/export") == (
        "/things/export?kind=a&sort=cost"
    )


def test_everything_gives_every_row_in_the_same_order(session):
    view = view_of({"sort": "cost", "dir": "desc", "size": "10"})
    assert [row.id for row in view.everything(session, select(THING.c.id))] == [2, 4, 3, 1]


def test_the_statement_a_page_sends_binds_every_value():
    view = view_of({"kind": "a", "q": "x"})
    compiled = select(THING.c.id).where(*view.conditions).compile(dialect=postgresql.dialect())
    assert "'a'" not in str(compiled)
    assert "'%x%'" not in str(compiled)
    assert len(compiled.params) >= 2


@pytest.mark.rule("USE-05")
def test_a_blank_value_in_an_address_is_kept_because_it_means_something():
    assert list_query("/things?kind=&sort=cost", "/things") == {"kind": "", "sort": "cost"}


@pytest.mark.parametrize("address", ["//[", "http://[", "http://[/things?kind=a", "//[/things", "http://a:b:c]/"])
def test_a_malformed_address_is_ignored_and_never_an_error(address):
    assert list_query(address, "/things") == {}


@pytest.mark.parametrize("address", ["/other?kind=a", "", "https://attacker.example/x?kind=a"])
def test_an_address_of_another_list_gives_nothing(address):
    assert list_query(address, "/things") == {}


def test_the_address_of_the_same_list_on_any_host_gives_its_query():
    assert list_query("http://testserver/things?kind=a", "/things") == {"kind": "a"}


def panelled(params: dict[str, str]) -> ListView:
    columns = (Column("name", "Name", THING.c.name),)
    return ListView.read("things", "/things", params, columns, THING.c.id, "name", panelled=True)


@pytest.mark.rule("USE-05")
def test_a_filter_panel_keeps_its_state_in_the_address():
    view = panelled({"panel": "hidden", "sort": "name", "dir": "desc"})
    assert view.panel == "hidden"
    assert view.here == "/things?dir=desc&panel=hidden"
    assert view.link(page=2) == "/things?dir=desc&page=2&panel=hidden"
    assert ("panel", "hidden") in view.hidden_fields
    assert view.panel_link("shown") == "/things?dir=desc&panel=shown"
    assert view.elsewhere("/things/export") == "/things/export?dir=desc"


@pytest.mark.parametrize("value", ["open", "<b>", "", "hidden "])
def test_a_panel_state_off_its_list_means_the_default(value):
    assert panelled({"panel": value}).panel == ""


def test_a_list_without_a_panel_ignores_the_word():
    assert view_of({"panel": "hidden"}).here == "/things"


def test_a_filter_cannot_take_a_name_the_address_uses():
    with pytest.raises(ValueError, match="cannot be called"):
        ListView.read("t", "/t", {}, (Column("n", "N", THING.c.name),), THING.c.id, "n", (Filter("panel", "P", []),))
