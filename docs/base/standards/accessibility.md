---
type: reference
title: "Standards: Accessibility"
description: "The accessibility rules, WCAG 2.2 level AA: each with its source and check, the scan and the pass by hand, and how the official examples are treated."
tags: [accessibility, standards]
---

# Accessibility

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
| A11Y-08 | Every field has a label; errors are listed in a summary, linked to the field, and say how to fix them | [WCAG 3.3.1](https://www.w3.org/TR/WCAG22/#error-identification), [3.3.2](https://www.w3.org/TR/WCAG22/#labels-or-instructions), [3.3.3](https://www.w3.org/TR/WCAG22/#error-suggestion), [GOV.UK error summary](https://design-system.service.gov.uk/components/error-summary/) | Automatic |
| A11Y-09 | When content is replaced, focus stays somewhere sensible and the change is announced | [WCAG 4.1.3](https://www.w3.org/TR/WCAG22/#status-messages), [2.4.3](https://www.w3.org/TR/WCAG22/#focus-order) | Automatic |
| A11Y-10 | A chart always has a text summary and its data as a table, and they remain without JavaScript or when the library fails to load | [WCAG 1.1.1](https://www.w3.org/TR/WCAG22/#non-text-content) | Automatic |
| A11Y-11 | Nothing moves or flashes on its own; animation respects `prefers-reduced-motion` | [WCAG 2.2.2](https://www.w3.org/TR/WCAG22/#pause-stop-hide), [2.3.3](https://www.w3.org/TR/WCAG22/#animation-from-interactions) | By hand |
| A11Y-12 | Usable at 320 pixels wide, without sideways scrolling | [WCAG 1.4.10](https://www.w3.org/TR/WCAG22/#reflow) | Automatic |
| A11Y-13 | A skip link is the first thing the keyboard reaches | [WCAG 2.4.1](https://www.w3.org/TR/WCAG22/#bypass-blocks), [GOV.UK skip link](https://design-system.service.gov.uk/components/skip-link/) | Automatic |
| A11Y-14 | Contrast of 3:1 for control borders and meaningful graphics | [WCAG 1.4.11](https://www.w3.org/TR/WCAG22/#non-text-contrast) | By hand |
| A11Y-15 | ARIA only where HTML has no answer | [WCAG 4.1.2](https://www.w3.org/TR/WCAG22/#name-role-value) | By hand |
| A11Y-16 | Every screen works with a keyboard alone, in an order that makes sense | [WCAG 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard), [2.4.3](https://www.w3.org/TR/WCAG22/#focus-order) | By hand |
| A11Y-17 | Usable at 200 % zoom | [WCAG 1.4.4](https://www.w3.org/TR/WCAG22/#resize-text) | By hand |

## Official examples

daisyUI's examples in the gallery are reference material, not our screens. The scan is no gate on them and never decides
what is shown: a person who asks to see what daisyUI offers sees all of it. It stays a gate on real screens: the shell,
the dashboard, the equipment list and detail, planning, the work order form, the settings menu with every look of its
controls, the gallery's index, the frame of component pages, error pages and the palette.

So **Available is not a promise of accessibility.** It means an official example, shown as published, not audited by us.
**Approved** means our macro, tests and a review. **Decorative** and **Not recommended** stay, with their notes. Before an
Available component reaches a real screen it gets a macro, and then it answers to these rules like any other.

Text inside an official example is left as published, in English, under `lang="en"`. The language checks skip those
regions, marked in the page, and not our frame around them.
