---
type: reference
title: Layouts
description: "The application's arrangements (menu, width, density, header, title) and how an organization and a person choose them"
tags: [base, layouts]
---

# Layouts

An application chooses its arrangement in its settings, starting from its organization's (see
[Your theme](your-theme.md#your-theme)). The [settings menu](settings-menu.md#settings-menu) shows each one live.

| Setting | Options | Typical use |
|---|---|---|
| `APP_LAYOUT_NAVIGATION` | `side`, `compact` (icons only), `top`, `hidden` (opened from a button) | Side for management applications; top for a few sections |
| `APP_LAYOUT_BAR` | `plain`, `brand` | `brand` draws the top bar and the menu in the theme called `bar` from `app/brand/theme.css`, with `app/brand/logo-bar.svg` if there is one |
| `APP_LAYOUT_STICKY_HEADER` | `true`, `false` | Fixed for long tables |
| `APP_LAYOUT_WIDTH` | `full`, `centered` | Full for tables; centred for forms |
| `APP_LAYOUT_DENSITY` | `normal`, `compact` | Compact for data-heavy screens |
| `APP_LAYOUT_THEME_CONTROL` | `dropdown`, `toggle`, `swap`, `radio` | How the header's theme control looks |
| `APP_LAYOUT_LANGUAGE_CONTROL` | `dropdown`, `select`, `menu` | How the header's language control looks |
| `APP_LAYOUT_PAGE_TITLE` | `page`, `header` | `header` puts the page's title in the top bar, for more room. It stays the page's one `h1`, and with `top` navigation it stays in the page, where the bar has no room |
| `APP_LAYOUT_LIST_WIDTH` | `page`, `wide` | `wide` lets every list use the whole width, whatever `APP_LAYOUT_WIDTH` says |
| `APP_LAYOUT_LIST_DENSITY` | `normal`, `dense` | `dense` gives every list smaller rows, a taller box and its wide-screen columns sooner |
| `APP_LAYOUT_CHOICES` | A list of `navigation`, `sticky_header`, `width`, `density`, `theme_control`, `language_control`, `page_title`, `list_width`, `list_density`; all by default | What each person may change. What is left out stays as set above; `[]` hides the menu |

On a phone the navigation is always a panel opened from a button, and the theme and language controls move into the user
menu.

The title in the top bar is the `h1` that `page_heading` would have written: the layout draws the content first, so the
macro can hand its title to the bar and keep its description and actions in the page. A page that writes its own `h1`,
as an error page does, keeps it. On a phone the title shortens with an ellipsis and the application's name leaves the
bar, and on paper the title is all that is left of it.
