---
type: reference
title: Standards
description: "Every rule that screens and components follow, each with its official source and how it is checked: accessibility, usability, language, components, data and security."
tags: [accessibility, usability, i18n, data, security, standards]
related: [specification.md, decisions.md]
---

# Standards

This page is the single home of the rules. Each one has an identifier, a source and a check, so quality does not depend
on anyone's opinion, an AI assistant's included. Tests name the rule they prove with `@pytest.mark.rule("A11Y-05")`.
`tests/test_standards.py` reads those marks from pytest's collection, so a comment or a string does not count. It fails
if a rule has no source, if a rule marked *Automatic* has no test, if a test names a rule that is not *Automatic*, or if
a row starting `| XXX-NN |` does not parse. Rules proved only on demo screens are listed in `tools/remove_demo.py` as
`ONLY_ON_DEMO`, and become *By hand* in a clone.

## Where the rules come from

| Area | Authority | What it is | Access |
|---|---|---|---|
| Accessibility | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | W3C Recommendation | Free |
| Accessibility | [EN 301 549](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/) | European standard for accessible ICT, published by ETSI | Free |
| Accessibility | [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) | W3C guidance for interactive patterns | Free |
| Usability | [GOV.UK Design System](https://design-system.service.gov.uk/) | Patterns researched with real users, by a government | Free; not a standard |
| Usability | [Nielsen's 10 heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) | The most cited usability reference | Free; not a standard |
| Language | [W3C Internationalization](https://www.w3.org/International/techniques/authoring-html) | W3C guidance for authoring pages | Free |
| Language | [BCP 47](https://www.rfc-editor.org/info/bcp47) | Internet standard for language tags | Free |
| Language | [Unicode CLDR](https://cldr.unicode.org/) | The reference data for formats and plurals | Free |
| Language | [GNU gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | The reference for message catalogues | Free |
| Data | [PostgreSQL](https://www.postgresql.org/docs/current/) and [SQLite](https://www.sqlite.org/docs.html) documentation | What each database promises | Free |
| Security | [OWASP ASVS 5.0](https://asvs.owasp.org/) | Verification standard for applications | Free |
| Security | [OWASP Top 10:2025](https://top10.owasp.org/2025/) | The reference list of web risks | Free |
| Security | [CWE Top 25](https://cwe.mitre.org/top25/) | Most dangerous software weaknesses | Free |
| Supply chain | [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final) and [SLSA](https://slsa.dev/spec/) | Secure development and build integrity | Free |

**Reading the tables.** A rule cites the public source it comes from. *Project decision* means no source requires it:
it is a choice of this repository, stated as such, and an organization may change it.

**Usability has no free, testable standard like WCAG.** The international standards exist,
[ISO 9241-110](https://www.iso.org/standard/75258.html) and [ISO 9241-210](https://www.iso.org/standard/77520.html),
but their text is sold, and **this repository does not use them**: nobody here has read them, and no rule rests on them.

**Check** says how a rule is verified: *Automatic* (a test proves the rule as written), *By hand* (in the pull request),
or the milestone that brings it.

To add a rule: find its source first, give it the next identifier, and add its test in the same change.

## Accessibility

The target is WCAG 2.2 level AA. An automatic scan finds only part of the failures, so each approved component also
passes by hand: keyboard only, then a screen reader (NVDA with a Chromium browser), recorded in its pull request.

| ID | Rule | Source | Check |
|---|---|---|---|
| A11Y-01 | Real headings, labels, tables, buttons and links: the scan finds no failure on real screens | [WCAG 1.3.1](https://www.w3.org/TR/WCAG22/#info-and-relationships), [4.1.2](https://www.w3.org/TR/WCAG22/#name-role-value) | Automatic |
| A11Y-02 | The Tab key reaches every visible control of the start page, in the order of the page, and Escape closes a menu and returns focus to its button | [WCAG 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard), [2.4.3](https://www.w3.org/TR/WCAG22/#focus-order) | Automatic |
| A11Y-03 | The keyboard is never trapped | [WCAG 2.1.2](https://www.w3.org/TR/WCAG22/#no-keyboard-trap) | By hand |
| A11Y-04 | Focus is visible on every control the Tab key reaches, and `scroll-padding-top` keeps it clear of the sticky header | [WCAG 2.4.7](https://www.w3.org/TR/WCAG22/#focus-visible), [2.4.11](https://www.w3.org/TR/WCAG22/#focus-not-obscured-minimum) | Automatic |
| A11Y-05 | Contrast of 4.5:1 for text and 3:1 for large text, by the scan on the pages it visits. It measures text against its own background, not whether a shape stands out from the page: that is USE-10. With daisyUI's themes as they come, coloured links, `btn-link`, `menu-title`, `chat-bubble-primary` and `chat-bubble-secondary` can fall below it, and are not used on real screens. A theme added to `theme.css` is computed too | [WCAG 1.4.3](https://www.w3.org/TR/WCAG22/#contrast-minimum) | Automatic |
| A11Y-06 | Targets of at least 24 by 24 pixels | [WCAG 2.5.8](https://www.w3.org/TR/WCAG22/#target-size-minimum) | Automatic |
| A11Y-07 | A status is never shown by colour alone | [WCAG 1.4.1](https://www.w3.org/TR/WCAG22/#use-of-color) | By hand |
| A11Y-08 | Every field has a label; errors are listed in a summary, linked to the field, and say how to fix them | [WCAG 3.3.1](https://www.w3.org/TR/WCAG22/#error-identification), [3.3.2](https://www.w3.org/TR/WCAG22/#labels-or-instructions), [3.3.3](https://www.w3.org/TR/WCAG22/#error-suggestion), [GOV.UK error summary](https://design-system.service.gov.uk/components/error-summary/) | Milestone 3 |
| A11Y-09 | When content is replaced, focus stays somewhere sensible and the change is announced | [WCAG 4.1.3](https://www.w3.org/TR/WCAG22/#status-messages), [2.4.3](https://www.w3.org/TR/WCAG22/#focus-order) | Automatic |
| A11Y-10 | A chart always has a text summary and its data as a table, and they remain without JavaScript or when the library fails to load | [WCAG 1.1.1](https://www.w3.org/TR/WCAG22/#non-text-content) | Automatic |
| A11Y-11 | Nothing moves or flashes on its own; animation respects `prefers-reduced-motion` | [WCAG 2.2.2](https://www.w3.org/TR/WCAG22/#pause-stop-hide), [2.3.3](https://www.w3.org/TR/WCAG22/#animation-from-interactions) | By hand |
| A11Y-12 | Usable at 320 pixels wide, without sideways scrolling | [WCAG 1.4.10](https://www.w3.org/TR/WCAG22/#reflow) | Automatic |
| A11Y-13 | A skip link is the first thing the keyboard reaches | [WCAG 2.4.1](https://www.w3.org/TR/WCAG22/#bypass-blocks), [GOV.UK skip link](https://design-system.service.gov.uk/components/skip-link/) | Automatic |
| A11Y-14 | Contrast of 3:1 for control borders and meaningful graphics | [WCAG 1.4.11](https://www.w3.org/TR/WCAG22/#non-text-contrast) | By hand |
| A11Y-15 | ARIA only where HTML has no answer | [WCAG 4.1.2](https://www.w3.org/TR/WCAG22/#name-role-value) | By hand |
| A11Y-16 | Every screen works with a keyboard alone, in an order that makes sense | [WCAG 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard), [2.4.3](https://www.w3.org/TR/WCAG22/#focus-order) | By hand |
| A11Y-17 | Usable at 200 % zoom | [WCAG 1.4.4](https://www.w3.org/TR/WCAG22/#resize-text) | By hand |

### Official examples

daisyUI's examples in the gallery are reference material, not our screens. The scan is no gate on them and never decides
what is shown: a person who asks to see what daisyUI offers sees all of it. It stays a gate on real screens: the shell,
the dashboard, the equipment list and detail, planning, the settings menu with every look of its controls, the gallery's
index, the frame of component pages, error pages and the palette.

So **Available is not a promise of accessibility.** It means an official example, shown as published, not audited by us.
**Approved** means our macro, tests and a review. **Decorative** and **Not recommended** stay, with their notes. Before an
Available component reaches a real screen it gets a macro, and then it answers to these rules like any other.

Text inside an official example is left as published, in English, under `lang="en"`. The language checks skip those
regions, marked in the page, and not our frame around them.

## Usability

| ID | Rule | Source | Check |
|---|---|---|---|
| USE-01 | Each screen designs its loading, empty, error, partial and no-permission states | [Nielsen 1: visibility of system status](https://www.nngroup.com/articles/ten-usability-heuristics/) | By hand |
| USE-02 | Messages say what happened and what to do, in plain language | [Nielsen 9: recover from errors](https://www.nngroup.com/articles/ten-usability-heuristics/), [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/) | By hand |
| USE-03 | A failed submission keeps what was typed | [GOV.UK validation](https://design-system.service.gov.uk/patterns/validation/) | Milestone 3 |
| USE-04 | Actions can be undone where possible; a confirmation names what will be lost | [Nielsen 3 and 5: user control, error prevention](https://www.nngroup.com/articles/ten-usability-heuristics/) | Milestone 3 |
| USE-05 | Filters, sort and page live in the URL, survive a reload and work with the back button | Project decision | Automatic |
| USE-06 | Any action responds at once; a long task shows progress and can be left running | [Nielsen 1: visibility of system status](https://www.nngroup.com/articles/ten-usability-heuristics/) | Milestone 4 |
| USE-07 | One primary action per screen | Project decision | By hand |
| USE-08 | The same thing looks and behaves the same, in the same place | [WCAG 3.2.3](https://www.w3.org/TR/WCAG22/#consistent-navigation), [3.2.4](https://www.w3.org/TR/WCAG22/#consistent-identification), [Nielsen 4: consistency](https://www.nngroup.com/articles/ten-usability-heuristics/) | By hand |
| USE-10 | Every milestone is looked at by a person, in both themes, at desktop and phone width, before it is merged: passing the checks says nothing about how it looks | Project decision | By hand |
| USE-09 | The theme follows the system; a person's choice is remembered | [Media Queries 5](https://www.w3.org/TR/mediaqueries-5/) | Automatic |

## Language

Every application can run in several languages from its first screen, because adding them later means touching every
text of every screen. A single-language application still follows these rules: they cost almost nothing, and formatting
applies anyway.

| ID | Rule | Source | Check |
|---|---|---|---|
| LANG-01 | No visible text in code: pages, messages and titles go through translation, and so will Excel headers and chart labels | [gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | Automatic |
| LANG-02 | Whole sentences, never joined from pieces: word order changes between languages | [gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | By hand |
| LANG-03 | Named placeholders, identical in source and translation | [gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | Automatic |
| LANG-04 | Plurals follow each language's rules | [CLDR plural rules](https://cldr.unicode.org/index/cldr-spec/plural-rules) | Automatic |
| LANG-05 | A context wherever one word has two meanings | [gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | By hand |
| LANG-06 | The formatters write numbers, dates and times as the locale does | [Unicode CLDR](https://cldr.unicode.org/) | Automatic |
| LANG-07 | A number is read as the person's language writes it, with the digits 0 to 9 and its own signs; a wrong format is refused, never guessed. A date is read only as YYYY-MM-DD, the form a date field sends | [Unicode CLDR](https://cldr.unicode.org/) | Automatic |
| LANG-08 | Exact values stay exact: the locale changes how a `Decimal` looks, never its value | Project decision | Automatic |
| LANG-09 | Moments are shown in the application's time zone | [W3C Working with Time Zones](https://www.w3.org/TR/timezone/) | Automatic |
| LANG-10 | `lang` on every page, and on any passage in another language | [WCAG 3.1.1](https://www.w3.org/TR/WCAG22/#language-of-page), [3.1.2](https://www.w3.org/TR/WCAG22/#language-of-parts), [BCP 47](https://www.rfc-editor.org/info/bcp47), [W3C](https://www.w3.org/International/questions/qa-html-language-declarations) | Automatic |
| LANG-11 | Layouts survive text 40 % longer | [W3C authoring](https://www.w3.org/International/techniques/authoring-html) | Automatic |
| LANG-12 | Each language is named in itself (Català, Español), without flags: a flag is a country | Project decision | Automatic |
| LANG-13 | A missing text falls back to the source language; never a blank or a key | [gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | Automatic |
| LANG-14 | No *fuzzy* text remains in a catalogue: fuzzy text is not finished | Project decision | Automatic |
| LANG-15 | Moments are stored in UTC. A column takes only a datetime with its time zone, and gives one back in UTC, on both databases | [W3C Working with Time Zones](https://www.w3.org/TR/timezone/) | Automatic |
| LANG-16 | No text in images; CSS logical properties | [W3C authoring](https://www.w3.org/International/techniques/authoring-html) | By hand |
| LANG-17 | A translation by AI stays *fuzzy* until a person accepts it | Project decision | By hand |
| LANG-18 | Screens use the formatters for numbers, dates and times, never their own | [Unicode CLDR](https://cldr.unicode.org/) | By hand |

### How a language is chosen

1. The person's saved choice.
2. The browser's `Accept-Language`, if the application offers it.
3. The application's default.

| Text | Language |
|---|---|
| Interface, messages, exports | The person's |
| Business data | As stored, unless the model declares it translatable |
| Logs and audit codes | The source language, so they can be searched |

A **glossary** per organization is [planned](specification.md#milestones). The demo ships in English, Spanish and
Catalan.

### How language is checked

| Check | Catches |
|---|---|
| `tools/translations.py check` | Texts missing from a catalogue, unfinished or fuzzy translations, different placeholders |
| A pseudo-language marks every translated text and lengthens it by 40 % | Any unmarked text was never translated, except inside [official examples](#official-examples); layouts that break with longer languages |
| Values fixed per language, written and read back | Formats, and decimals that change |

## Components

| ID | Rule | Source | Check |
|---|---|---|---|
| COMP-01 | The catalogue lists every official component, plus an organization's own, each of those with a hand-written page; official pages match the official file. These pages are a reference for assistants; the gallery's examples come from daisyUI's documentation source | [daisyUI llms.txt](https://daisyui.com/llms.txt) | Automatic |
| COMP-02 | Every component has a page with frontmatter and a description; each official page shows its status; one with problems says why | Project decision | Automatic |
| COMP-03 | The gallery shows every component with its status and every official example, counted from daisyUI's documentation, and generated data matches that documentation. A macro appears on the page of its component | Project decision | Automatic |
| COMP-04 | A class in use must exist, read from real pages, macro arguments, `{% set %}` values and the catalogue; values such as `[color:#ff0000]` are refused. Component classes outside what Tailwind reads are caught; Tailwind utilities in Python files are not | Project decision | Automatic |

## Data

Where the two databases [differ](specification.md#where-the-two-databases-differ) is stated in the specification. These
rules are what holds on both. The tests of `DATA-02` to `DATA-06` and `LANG-15` run on SQLite everywhere, and on PostgreSQL
in the Ubuntu job.

| ID | Rule | Source | Check |
|---|---|---|---|
| DATA-01 | Production runs on PostgreSQL: the application refuses to start on anything else, and SQLite is the default only with `APP_ENVIRONMENT=development` | [SQLite: appropriate uses](https://www.sqlite.org/whentouse.html) | Automatic |
| DATA-02 | Money and quantities use one exact column type: `Numeric(38, 20)` on PostgreSQL, text on SQLite, written in one form. A float is refused, on writing and in a query, and so is a value the column cannot hold whole. No model or migration declares another decimal type | [PostgreSQL numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html), [Python decimal](https://docs.python.org/3/library/decimal.html) | Automatic |
| DATA-03 | On SQLite, ordering and comparing an exact column are numeric, and a sum, a function, arithmetic, a cast or a case over one, built with SQLAlchemy, fails loudly instead of going through a float. `total()` gives the same exact sum on both databases | [SQLite collation](https://www.sqlite.org/datatype3.html#collation), [SQLite aggregates](https://www.sqlite.org/lang_aggfunc.html) | Automatic |
| DATA-04 | Foreign keys hold on both databases | [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html#fk_enable) | Automatic |
| DATA-05 | A route that uses the database is declared with `def`, so a query runs in a worker thread and does not stop the server | [FastAPI: concurrency](https://fastapi.tiangolo.com/async/) | Automatic |
| DATA-06 | Models and migrations say the same on both databases, every migration goes down and up again, and a batch change keeps the rows that point to its table | [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html), [Alembic batch](https://alembic.sqlalchemy.org/en/latest/batch.html) | Automatic |
| DATA-07 | Demo data is generated: the same seed and the same number of rows give the same rows on any computer and Python, and no real person or company appears | Project decision | Automatic |

## Security

| ID | Rule | Source | Check |
|---|---|---|---|
| SEC-01 | Identity comes only from the proxy, and a repeated identity header means no identity; without it, nothing is served except `/health` and `/static/` | [ASVS V6](https://asvs.owasp.org/), [Top 10 A07](https://top10.owasp.org/2025/) | Automatic |
| SEC-02 | Permissions are checked on the server, per action; hiding a button is not a control | [ASVS V8](https://asvs.owasp.org/), [Top 10 A01](https://top10.owasp.org/2025/) | Automatic |
| SEC-03 | Input is validated at the edge | [ASVS V2](https://asvs.owasp.org/), [Top 10 A05](https://top10.owasp.org/2025/) | Milestone 3 |
| SEC-04 | Escaping is always on; user data is never marked as safe | [ASVS V1](https://asvs.owasp.org/), [CWE Top 25](https://cwe.mitre.org/top25/) | Automatic |
| SEC-05 | Queries are parameterised; no text built from input | [ASVS V1](https://asvs.owasp.org/), [CWE Top 25](https://cwe.mitre.org/top25/) | Automatic |
| SEC-06 | A Content Security Policy without inline scripts or styles, on every page, official examples included: none reaches a page with `style=`, `on*=` or an address on another server, and a browser opening each page finds no violation | [CSP 3](https://www.w3.org/TR/CSP3/), [OWASP CSP](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html) | Automatic |
| SEC-07 | Changes from another site are refused | [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Fetch Metadata](https://www.w3.org/TR/fetch-metadata/) | Automatic |
| SEC-08 | Only the personal data needed; none in logs or URLs | [ASVS V14](https://asvs.owasp.org/), [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | By hand |
| SEC-09 | Secrets stay out of the repository: every text file git tracks is scanned for obvious ones, and `.env` is ignored | [ASVS V13](https://asvs.owasp.org/) | Automatic |
| SEC-10 | Every package in `uv.lock` has hashes, each supported platform has an executable hash, and each copied file matches its recorded hash | [Top 10 A03](https://top10.owasp.org/2025/), [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final), [SLSA](https://slsa.dev/spec/) | Automatic |
| SEC-11 | An error reveals nothing to the person, and its detail reaches the log | [ASVS V16](https://asvs.owasp.org/), [Top 10 A10](https://top10.owasp.org/2025/) | Automatic |
| SEC-12 | Uploads are checked by size and real type | [ASVS V5](https://asvs.owasp.org/), [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Milestone 3 |
| SEC-14 | Text is never run as code: no `eval`, `new Function` or `exec`, and the browser refuses them | [CWE-95](https://cwe.mitre.org/data/definitions/95.html), [CSP 3](https://www.w3.org/TR/CSP3/), [htmx security](https://htmx.org/essays/web-security-basics-with-htmx/) | Automatic |
| SEC-15 | A spreadsheet never runs what it exports: text that could start a formula is neutralised, and no cell holds one | [OWASP CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection) | Automatic |
| SEC-13 | Cookies are `HttpOnly` and `SameSite`, and `Secure` in production; a redirect never leaves the application | [ASVS V3](https://asvs.owasp.org/), [Top 10 A01](https://top10.owasp.org/2025/) | Automatic |
