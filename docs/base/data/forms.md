---
type: reference
title: Forms
description: "How to build a form to add or change a row: field macros, validation, errors and what is kept after a failed save"
tags: [base, data, forms]
---

# Forms

The work order form is the pattern of the planning editor, grown up: `/work-orders/new` and `/work-orders/<id>/edit`,
reached from Planning and from the equipment detail, and needing the `admin` role, as editing does.

| What | How |
|---|---|
| Fields | One macro per kind of field, all with a visible label, as the [gallery](../gallery.md#gallery) shows. A hint and an error reach the control through `aria-describedby`, and `aria-invalid` marks the error |
| Checking | `app/core/forms.py`, at the edge, as [SEC-03](../standards.md#security) says. A reader takes text and gives the value to save, or raises `Refused` with what the person should read. `read_fields` runs them all, so every problem shows at once. The browser's `required` and `maxlength` help a person; forms are `novalidate`, and the server decides |
| Text | Trimmed, one form of line break, its length checked, and refused by Unicode category: control and format characters. Tab and line breaks pass in several lines, and line and paragraph separators count as line breaks. PostgreSQL refuses a NUL, which would be an error page there and stored on SQLite, and the others hide on screen. Two exceptions come from pasted text: soft hyphens, zero width spaces and byte order marks are removed, since a person cannot see them to take them out, and joiners stay, since they are part of an emoji or a word. File names have no exceptions |
| Numbers and dates | `read_decimal` and `read_whole` through `parse_decimal`, and `read_date` through `parse_date`, with limits, because a year typed as 0026 is a valid date and a mistake. Never a float. Generated costs have twenty decimals, so the cost field shows every one and a form nobody changed saves the same value |
| A failed save | The form comes back with what was typed, an error summary whose links land on the fields, and focus on it. A 422 page without JavaScript, the form alone in its place with htmx |
| A date typed halfway | A browser sends such a field as nothing, which would clear an optional date in silence, so `app.js` tells the server, and it asks for the date. The value cannot come back: the browser does not give it |
| A saved form | Back where the person came from, Planning or the equipment page, with their filters. The address says what happened, for that one page, as `saved` or `deleted`; a number that does not fit says nothing. `way_back` rebuilds the address from what it can read, so it never leaves those two screens |
| Deleting | With a [confirmation](../components/confirmation-dialog.md) that names the row, in a dialog with htmx, and on a page of its own without JavaScript. The form that deletes is a plain POST in both |
| A form that is not one | A file sent for a text field or a part too long is a 400 page. FastAPI's own answer repeats what was sent |

The equipment is asked for by its code. A searchable select holds its options in the page, because without JavaScript it
is a plain select, and 50,000 of them is a page of megabytes. So the searchable select is the list of faults.
