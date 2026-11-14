---
type: reference
title: "Decisions: Language, numbers and time"
description: "Why language support from the first screen, Babel and CLDR for formats, translations from `.po` files, UTC, decimal contexts, rounding and identifiers."
tags: [decisions, language]
---

# Language, numbers and time

| Decision | Why | Rejected |
|---|---|---|
| Language support from the first screen | Adding it later touches every text | Single language first |
| UTC as the default time zone | The base belongs to no place; an application sets its own in `APP_TIME_ZONE` | The time zone of whoever wrote it |
| Translations read directly from `.po` files | Nothing to compile | Compiled `.mo` files |
| Babel for formats and translations | Pure Python, one dependency for both jobs, and the usual choice for Python web applications | PyICU: closer to CLDR, but it has no ready package, must be compiled on each server, ties its version to the system, and handles no `.po` files |
| CLDR's `minimumGroupingDigits` applied through Babel's own `group_separator` | The standard says 1250 and 12.500 in Spanish, and Babel ignores that field. The values come from Unicode's data for the CLDR version Babel uses (`tools/cldr_grouping.py`), and a test fails if they part ways. Delete it if Babel adds support | A list written by hand, which was wrong for regional variants; accepting the difference, which only affects how numbers look |
| Decimal context sized to each value | Python's default of 28 digits, or any fixed limit, cuts longer values without an error | A fixed precision |
| Rounding half up, `rounded()` in the formatters | What a person and Excel's `ROUND` expect, in one place for the screen and the export. Python's default, half even, would make a screen and a sheet disagree | Half even |
| An identifier has no thousands separator | It is a name, not a quantity: *4059* is how a person repeats it | Formatting every number alike |
| Spanish and Catalan words for the icon search, kept here | Lucide's tags are English: alone they find the right icon for 3 of our 108 Spanish words and 4 of 108 Catalan ones. A short list of common business words, each tested to point at a real icon, fixes that | Translating every tag: thousands of words to keep in step with each version |
