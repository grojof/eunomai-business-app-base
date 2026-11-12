# Changelog

## 0.1.1 (2026-11-12)

`tools/update_application.py` needs git 2.40 or later and says so when there is none or an older one; its tests are skipped there. In a test of an application on a person's computer, which has no git on purpose, and in an assistant's sandbox, whose git is older, they failed with nine errors that were not the application's.

## 0.1.0 (2026-11-11)

The first version, for organizations to make their template from: a working demo of its components, lists, forms,
boards, calendars, timelines, charts and Excel exports on SQLite and PostgreSQL, identity from a trusted proxy with
roles from groups, two themes and three languages, accessibility and contrast checked in both themes, a module
generator (`tools/new_module.py`), an organization's template (`tools/make_template.py`) and the update of an
application made from it (`tools/update_application.py`). See [the specification](docs/base/specification.md).
