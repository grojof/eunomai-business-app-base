---
type: reference
title: Identity
description: "How a person is identified: the trusted proxy, its headers, groups mapped to roles, and a fake identity for local work"
tags: [base, identity]
---

# Identity

The application has no login of its own. A trusted reverse proxy authenticates the person and passes who they are in
headers; the header names and the mapping from groups to roles are settings. Those headers are believed only from the
addresses in `APP_TRUSTED_PROXIES`, by default this computer. Uvicorn listens on `127.0.0.1` by default and must run
with `--no-proxy-headers`: otherwise it replaces the proxy's address with the one in `X-Forwarded-For`, and everyone
gets 401. A repeated identity header means no identity.

Roles come from groups, in `APP_ROLE_GROUPS`. A `*` in a group stands for any text, so a family of groups gives one
role: `{"admin": ["app-admins"], "manager": ["departamento-*"]}`. Which one matched, a department for example, is the
application's own to read from the person's groups: the base knows nothing of what a group means. Everyone the proxy
identified also has `signed_in`, which no group gives: a screen open to all of them asks for it, and who may come in
at all is the proxy's, or Entra's, to decide.

| Roles | How |
|---|---|
| None: whoever comes in may do everything | `role = "signed_in"` in each module; nothing in `APP_ROLE_GROUPS` |
| Fixed, from the directory's groups | `APP_ROLE_GROUPS`, each role and its groups |
| One role from a family of groups, and what it covers from which | A pattern in `APP_ROLE_GROUPS`; the application reads the matching group from `Person.groups` |
| Managed in the application, with the directory giving only who comes in | Not in the base: a module of the application's own, for whom may see that screen |

A visitor without identity gets the 401 page, with no navigation, version or user menu. The public paths are exactly
`/health` and `/static/`. For local work, a fake identity is available and refuses to start outside development.
