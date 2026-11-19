---
type: how-to
title: A static application
description: "How an application whose pages need nothing from a server is published as files: tools/export_static.py, what it writes, what it refuses, and how theme, language and search work without a server"
tags: [base, static-export, deployment]
related: [deployment.md, identity.md, command-palette.md]
---

# A static application

Some applications do all their work in the browser: a calculator, a generator of labels, a guide. They read no
database and save nothing, so the server that runs them only repeats the same pages. Such an application is published
as files instead: no process to keep running and no database, behind the same reverse proxy that signs people in.

```bash
uv run --frozen python tools/export_static.py static-export
```

The application is written the same way as any other, with the same shell, macros and checks, and runs with its
server while it is built. The exporter is what decides whether it can live without one: it writes all of it, or
nothing and every reason why not.

## What it writes

| In `<output>/` | What it is |
|---|---|
| `site/` | The folder to serve, at the root of its host |
| `site/index.html` | The first page: it sends each person to their language's folder |
| `site/<language>/` | Every page in that language: `/guide` is `site/en/guide/index.html`, served as `/en/guide/` |
| `site/<language>/search.html` | What the [command palette](command-palette.md#command-palette) finds, in that language |
| `site/<language>/404.html` | The page for an address that is not there, in that language |
| `site/404.html` | The same page in the default language, for a proxy that answers every missing address with one file |
| `site/static/` | The application's own files, at the addresses its pages name: `app/ui/static/` with the copied libraries, the images and fonts of `app/brand/`, and any folder of files a module mounts |
| `headers.json` | The HTTP headers the proxy must send with every file, as a JSON object: the Content Security Policy and the others the application itself sends, read from the same place in the code |

It ends with 0 only when everything is there. Otherwise it ends with 1, prints the reasons to the error output, one
a line, and leaves `<output>` as it was: a last good export is never half replaced.

Settings come from the environment, as the application's own (`APP_NAME`, `APP_TIME_ZONE`, `APP_LANGUAGES`,
`APP_LAYOUT_*`...), and no `.env` is read. Some are the exporter's own, whatever the environment says: it runs as
production does, with a database address nothing connects to, a made-up person who has no group and so the
`signed_in` role alone, and no layout a person may change. It needs the development packages (`uv sync --frozen`,
not `--no-dev`), so run it where the application is built, as a user with no privileges, and publish only `site/`:
nothing it installs to build is served.

## What changes on the pages

| Piece | With a server | Exported |
|---|---|---|
| Who is signed in | The proxy's headers; the user menu shows the name | Nobody is known to the pages: no user menu. The proxy still decides who may open them |
| Theme | A cookie the server reads | Kept by the browser (`localStorage`), and put on the page by `preferences.js` before anything is painted. Without a choice, the system's |
| Language | A cookie, then the browser's languages | A folder for each. The control is links to the same page in the other folders; the first page goes to the language last chosen, then to the first of the browser's that is offered, then to the default, and without JavaScript shows the links |
| Search | `/search`, made for each person | `search.html` in each folder, with what everyone signed in may open |
| Layout | The application's, and what a person changes in `/settings` | The application's alone: no settings menu, no folding menu, no list options |
| Theme and language on a small screen | In the user menu | In a *Preferences* menu with nobody's name |
| Security headers | Sent by the application | Sent by the proxy, from `headers.json` |
| Links | As written: `/guide` | Rewritten into the language's folder: `/en/guide/`. A link with `hreflang` goes to that language's folder |

Nothing in an application's own templates changes for this: the exporter rewrites the links of each page it writes.
A template can ask `{% if static %}` where a piece only makes sense with a server.

## What it refuses

The exporter refuses what it can see needs a server ([SEC-17](standards/security.md#security)): what a route
declares, and what a page holds once it is drawn. That is all it promises. Routes are refused before anything is
drawn, and pages after:

| Refused | Why |
|---|---|
| A route that is not `GET` | A change needs a server |
| A route with a parameter in its address | Its pages are made when asked for |
| A route that takes `DatabaseSession`, or opens the database | There is no database |
| A route that reads a form, an uploaded file, the query, a header or a cookie | Nobody is there to read them |
| A route that asks for a role other than `signed_in` | Every file is the same for everyone the proxy lets in |
| A page that does not answer 200 with HTML: an error, a redirect, a download, JSON | It is not a page to write |
| `<form method="post">`, a button's `formaction`, or a form with an `action` | Its fields would go nowhere. A form with neither, handled by the page's own script, is fine, and so is `method="dialog"` |
| `hx-get`, `hx-post`, `hx-put`, `hx-patch`, `hx-delete`, and `sse-connect`, `ws-connect`, `hx-sse`, `hx-ws` | htmx asks the server for a piece of the page, or keeps a connection to it |
| `data-url`, or a calendar that fetches its events or sends a move | The same, from the base's scripts. A calendar with its events in the page and nothing to move is fine |
| A link to a page that is not exported, in a page or in the search | It would lead nowhere |
| A link with a query, such as `?page=2` | Only a server reads it. A link with a fragment, `#part`, is fine |
| An address under `/static/` with no file behind it, in a page or in a stylesheet | The page would be broken |
| Anything a page loads from an address that is not a file of the export: `src`, each address of a `srcset`, a stylesheet's or an SVG's `href`, `poster`, an `<object>`'s `data`, `ping` | The same. An address on another site is left to the policy |
| A relative address in any of those, such as `src="photo.png"` | The page moves into its language's folder, and the address would no longer lead to the file: write it from the root |
| `<meta http-equiv="refresh">` to an address of the application | The export cannot place it in a language's folder: use a link |
| A link among the files to copy (a symbolic link or a junction) | It would be copied as what it points at, which could be any file of the computer that makes the export |

The core's own `/health`, `/search`, `/settings` and `/preferences` are not pages and are left out.

**What it cannot see.** It reads what a route declares, not its code, and a page's HTML, not what its scripts do:

| Not detected | What happens |
|---|---|
| A route that reads `request.query_params`, `request.headers`, `request.cookies` or `request.state.person` by hand, without declaring a parameter | The page is exported as it is drawn for the exporter's request: no query, a made-up person. It will not change with the address or the person |
| A script of the application's own that calls the server (`fetch`, a form it sends itself) | The call fails once served as files. The policy in `headers.json` lets it reach no other host |
| What a script writes into the page after it loads: links, images | Not checked and not rewritten: such a link must name the language's folder itself |

An application written for this keeps to what is declared and what is in the page; those three are a person's to
check in a review.

## Serving it

[Deployment](deployment.md#an-application-with-no-server) says what the proxy must do. In short: `site/` at the root
of a host of its own, every header of `headers.json` on every answer, sign-in in front as for any application, and
never opened from the disk as `file://`, where the addresses and the policy mean nothing.

## Why this way

| Decision | Why |
|---|---|
| The exporter decides, not a setting | A flag in the environment could strip the identity from a running application. `static` is set only on the application the exporter builds for itself, and a test proves no setting reaches it |
| All or nothing | Half an application as files looks whole until someone presses the button that needed the server |
| Links rewritten by the exporter | A helper to call for each link would have to be in every template, macro and search item, and one forgotten would work with a server and break in the export. The exporter sees every link of every page and fails on the one it cannot place |
| A folder for each language | A file cannot choose a language. Each page keeps a real address in each language, with `lang` and `hreflang`, and works without JavaScript |
| A folder of files, not one self-contained file | The policy forbids inline scripts and styles, and one file would need a looser one; languages, the search and the libraries loaded only where used would all go inline |
| The theme in `localStorage`, read by a script in the head | Without a server, only a script can read the choice; outside the page so the policy allows it, and not deferred so the page is never painted in the wrong theme |
