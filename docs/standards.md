---
type: reference
title: Standards
description: "The rules every screen and component follows for accessibility, usability, language and security, and how each one is checked."
tags: [accessibility, usability, i18n, security, standards]
related: [specification.md, decisions.md]
---

# Standards

Every screen and component meets these rules. A rule without a check is a wish, so each section says how it is verified
and what still needs a person.

## Accessibility

The target is [WCAG 2.2](https://www.w3.org/TR/WCAG22/) level AA. Patterns follow the
[ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/), and component behaviour takes the
[GOV.UK Design System](https://design-system.service.gov.uk/) as its reference, because it publishes research with users
of assistive technology. The behaviour is adopted, not the look.

| Rule | In practice |
|---|---|
| HTML first | Real headings, labels, tables, buttons and links; ARIA only where HTML has no answer |
| Keyboard | Everything works without a mouse, in a logical order, with no trap |
| Visible focus | Always visible, in both themes, and never hidden behind a fixed bar |
| Contrast | 4.5:1 for text, 3:1 for large text, controls and meaningful graphics |
| Target size | At least 24 by 24 pixels |
| Not by colour alone | A status has text or an icon as well |
| Forms | Every field has a label; errors are named in a summary, linked to the field, and say how to fix it |
| Page changes | When htmx replaces content, focus stays somewhere sensible and the change is announced |
| Charts | Always a text summary and the data as a table |
| Movement | Nothing moves or flashes on its own; animation respects `prefers-reduced-motion` |
| Zoom | Usable at 200 % zoom and at 320 pixels wide, without horizontal scrolling of the page |

**How it is checked.** axe-core on every catalogue state, in both themes, and keyboard tests in the browser. An automatic
scan finds only part of the problems, so each component also passes by hand: keyboard only, then a screen reader (NVDA
with a Chromium browser), recorded in its pull request.

## Usability

| Rule | In practice |
|---|---|
| Every state is designed | Loading, empty, error, partial and no permission, in each screen |
| Say what happened and what to do | Messages in plain language, without error codes as the main text |
| Keep the person's work | A failed submission keeps what was typed; leaving unsaved changes asks first |
| Reversible or confirmed | Delete with undo where possible; a confirmation names what will be lost |
| The URL holds the state | Filters, sort and page survive a reload and can be shared |
| Immediate response | Any action shows a response at once; a long task shows progress and can be left running |
| One primary action per screen | The next step is obvious |
| Same thing, same place | A component behaves the same everywhere |
| Theme | Follows the system by default; the person can choose and it is remembered |

**How it is checked.** A review list per screen in the pull request, and the catalogue, where every state must exist.

## Language

Every application can run in several languages from its first screen, because adding them later means touching every
text of every screen. A single-language application still follows these rules: it costs almost nothing, and the
formatting rules apply anyway.

### Rules

| Rule | In practice |
|---|---|
| No visible text in code | Python, templates, messages, Excel headers, chart labels and page titles all go through gettext |
| Whole sentences | Never joined from pieces: word order changes between languages |
| Named placeholders | `%(name)s`, so a translator can move them |
| Real plurals | `ngettext`: languages differ in how many plural forms they have |
| Context | `pgettext` where one word has two meanings |
| Formats from the locale | Numbers, dates, times and currency through [Babel](https://babel.pocoo.org/) and [CLDR](https://cldr.unicode.org/), never by hand |
| Input follows the locale | A decimal is read as the person's locale writes it, and the form shows the expected format |
| Exact values stay exact | `Decimal` from the database to the page; the locale changes how it looks, never its value |
| Moments | Stored in UTC, shown in the person's time zone |
| Language is declared | `<html lang>` on every page, and `lang` on any passage in another language ([WCAG 3.1](https://www.w3.org/TR/WCAG22/#readable)) |
| Layout survives translation | No fixed widths around text and no text in images; CSS logical properties, so right-to-left stays possible |
| Selector | Each language named in itself (Català, Español), never with a flag: a flag is a country |

### Which language is used

1. The person's saved choice.
2. The browser's `Accept-Language`, if the application offers it.
3. The application's default.

The choice is remembered, and htmx responses use it too. A text missing from a language falls back to the default
language and is reported, never shown as a blank or a key.

| Text | Language |
|---|---|
| Interface, messages, exports | The person's |
| Business data | As stored, unless the model declares it translatable |
| Logs and audit codes | The source language, so they can be searched |

### Quality of translations

- A **glossary** per organization fixes key terms and tone, so "order" is translated the same way everywhere.
- A translation made by AI is marked as *fuzzy* until a person accepts it, and a fuzzy text never counts as finished.
- The demo ships in English, Spanish and Catalan, which proves plurals and different text lengths.

### How language is checked

| Check | Catches |
|---|---|
| Extraction finds no difference with the catalogue | Text added without its translation entry |
| No missing or fuzzy entry in a required language | Unfinished translations |
| Placeholders match between source and translation | Broken messages |
| A scan of rendered pages against a pseudo-language | Hard-coded text: any text not transformed was not translated |
| The pseudo-language lengthens text by 40 % | Layouts that break with longer languages |
| Every page has a valid `lang` | Wrong pronunciation in a screen reader |
| Number and date tests per locale, with fixed values | Formats, and decimals read back unchanged |

## Security

| Rule | In practice |
|---|---|
| Identity from the proxy only | Headers believed only behind it; see [Identity](specification.md#identity) |
| Permissions on the server | Checked per action; hiding a button is not a control |
| Input validated at the edge | Pydantic models; uploads checked by size and real type |
| Escaping always on | Never marking user data as safe |
| Parameterised queries | SQLAlchemy; no text built from input |
| Content Security Policy | No inline scripts; hence Alpine's CSP build |
| Changes protected | CSRF protection on every change |
| Personal data | Only what is needed; none in logs or URLs |
| Secrets | In the environment; a `.env.example` documents them |
| Dependencies | Pinned with hashes; checked for known vulnerabilities in every build |

**How it is checked.** Tests per role and per action, the headers of every response, and a dependency scan in CI.
