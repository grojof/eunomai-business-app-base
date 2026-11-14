---
type: reference
title: "Standards: Language"
description: "The language rules: how a language is chosen and checked, and how texts, numbers and dates follow it, each with its source and check."
tags: [i18n, standards]
---

# Language

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

## How a language is chosen

1. The person's saved choice.
2. The browser's `Accept-Language`, if the application offers it.
3. The application's default.

| Text | Language |
|---|---|
| Interface, messages, exports | The person's |
| Business data | As stored, unless the model declares it translatable |
| Logs and audit codes | The source language, so they can be searched |

A **glossary** per organization is [planned](../milestones.md#milestones). The demo ships in English, Spanish and
Catalan.

## How language is checked

| Check | Catches |
|---|---|
| `tools/translations.py check` | Texts missing from a catalogue, unfinished or fuzzy translations, different placeholders |
| A pseudo-language marks every translated text and lengthens it by 40 % | Any unmarked text was never translated, except inside [official examples](accessibility.md#official-examples); layouts that break with longer languages |
| Values fixed per language, written and read back | Formats, and decimals that change |
