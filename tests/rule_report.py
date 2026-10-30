"""A pytest plugin: writes which rule each collected test names, so tracing reads pytest's markers, not the text."""

import json
import os
from pathlib import Path

import pytest


def pytest_collection_finish(session: pytest.Session) -> None:
    found = [[item.nodeid, mark.args[0]] for item in session.items for mark in item.iter_markers("rule")]
    Path(os.environ["RULE_REPORT"]).write_text(json.dumps(found), encoding="utf-8")
