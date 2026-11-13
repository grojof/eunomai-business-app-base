---
type: reference
title: Settings menu
description: "The settings page every application has: what a person can change and how it is kept"
tags: [base, settings-menu]
---

# Settings menu

`/settings` belongs to the shell, in `app/core/` and `app/ui/`, so a clone keeps it. It is reached from the user menu and
the [command palette](command-palette.md#command-palette), and in the demo from the sidebar too. Each choice is a form sent to
`/preferences`, which accepts only the values in `LAYOUTS`, saves them in cookies as theme and language are saved, and
sends the person back. No inline script or style is needed, and focus returns to the control that was used.

| Section | Offers |
|---|---|
| Layout | Navigation, fixed header, width, density, the page's title, and the width and rows of lists |
| Theme and language | Theme: as the system, light, dark. Language |
| How the theme control looks | daisyUI's `theme-controller` as a dropdown, toggle, swap or radio, each live on the page |
| How the language control looks | A dropdown, a select with its own button, or a menu list, each live on the page |

The two last sections exist so that an organization can compare what daisyUI offers on real controls, then fix one with
`APP_LAYOUT_THEME_CONTROL` and `APP_LAYOUT_LANGUAGE_CONTROL` and leave it out of `APP_LAYOUT_CHOICES`. A toggle and a swap
have two states, so they cannot choose *as the system*: they show what is on screen, and the first change fixes a theme.
The select has a button because arrow keys change a closed select, and sending the form on each would change the
language under a person who is only reading the list.
