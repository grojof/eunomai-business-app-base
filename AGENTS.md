# AGENTS.md — business-app-base

For anyone working in this repository, person or AI assistant. The repository is in English and names no organization,
person or real system: it stays neutral so anyone can clone it.

## What goes where

| Folder | Contents | Rule |
|---|---|---|
| `app/core/` | Identity, roles, settings, database, languages, formatters, errors, health | Never imports from `app/demo/` |
| `app/ui/` | Components as macros, the stylesheet's source, the few JavaScript files | Screens call macros; daisyUI classes stay here where possible |
| `app/brand/` | The theme, logos | The only folder an organization must change |
| `app/demo/` | Demo screens, data and their translations | Deleting it leaves a working application |

## Rules

- Read [Standards](docs/standards.md) before writing a screen or a component. It is the only home of the rules: each
  has an identifier, an official source and a check. A change that breaks one is not finished, whatever else it does.
- Base decisions on those sources, not on what seems right. A new rule needs its source and its test, or it says
  *Project decision*. A test names the rule it proves: `@pytest.mark.rule("A11Y-05")`.
- Build the plain HTML first: it must work with a keyboard and a screen reader before any behaviour is added on top.
- Every text a user can see goes through translation. Every number, date and time goes through the locale's formatter.
- Colours come from the brand. No invented values such as `bg-[#ff0000]` or `text-[13px]`: a test refuses them.
- Use the existing macros before writing anything new. After changing templates, run `uv run python tools/css.py`.
- Each screen handles its empty, loading, error and no-permission states.
- A new component needs its page in the demo and its tests, in the same change.
- Add a dependency only if the [stack](docs/specification.md#stack) needs it. Pin it and check it for known
  vulnerabilities.
- No secrets in the repository, and no real people or companies in demo data.

## Checks

Automatic checks are what protect this repository; these rules only explain them. Run them all before calling something
done, and say plainly what was not checked. Where a check cannot tell, such as how a screen reader announces a change,
test by hand and record it in the pull request.

```bash
uv run ruff check && uv run ruff format --check && uv run mypy
uv run python tools/vendor.py check
uv run python tools/css.py check
uv run python tools/translations.py check   # after changing texts: tools/translations.py update
uv run pytest -q
```

Browser tests use the Chrome already on the computer; nothing is downloaded. After upgrading Babel, a test may ask for
`uv run python tools/cldr_grouping.py`.
