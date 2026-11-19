---
type: reference
title: "Standards: Security"
description: "The security rules applications inherit, each with its official source and how it is checked."
tags: [security, standards]
---

# Security

| ID | Rule | Source | Check |
|---|---|---|---|
| SEC-01 | Identity comes only from the proxy, and a repeated identity header means no identity; without it, nothing is served except `/health` and `/static/` | [ASVS V6](https://asvs.owasp.org/), [Top 10 A07](https://top10.owasp.org/2025/) | Automatic |
| SEC-02 | Permissions are checked on the server, per action; hiding a button is not a control | [ASVS V8](https://asvs.owasp.org/), [Top 10 A01](https://top10.owasp.org/2025/) | Automatic |
| SEC-03 | Input is validated at the edge | [ASVS V2](https://asvs.owasp.org/), [Top 10 A05](https://top10.owasp.org/2025/) | Automatic |
| SEC-04 | Escaping is always on; user data is never marked as safe | [ASVS V1](https://asvs.owasp.org/), [CWE Top 25](https://cwe.mitre.org/top25/) | Automatic |
| SEC-05 | Queries are parameterised; no text built from input | [ASVS V1](https://asvs.owasp.org/), [CWE Top 25](https://cwe.mitre.org/top25/) | Automatic |
| SEC-06 | A Content Security Policy without inline scripts or styles, on every page, official examples included: none reaches a page with `style=`, `on*=` or an address on another server, and a browser opening each page finds no violation. An application exported as files gives its proxy the same headers to send | [CSP 3](https://www.w3.org/TR/CSP3/), [OWASP CSP](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html) | Automatic |
| SEC-07 | Changes from another site are refused | [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [Fetch Metadata](https://www.w3.org/TR/fetch-metadata/) | Automatic |
| SEC-08 | Only the personal data needed; none in logs or URLs | [ASVS V14](https://asvs.owasp.org/), [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | By hand |
| SEC-09 | Secrets stay out of the repository: every text file git tracks is scanned for obvious ones, and `.env` is ignored | [ASVS V13](https://asvs.owasp.org/) | Automatic |
| SEC-10 | Every package in `uv.lock` has hashes, each supported platform has an executable hash, and each copied file matches its recorded hash | [Top 10 A03](https://top10.owasp.org/2025/), [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final), [SLSA](https://slsa.dev/spec/) | Automatic |
| SEC-11 | An error reveals nothing to the person, and its detail reaches the log | [ASVS V16](https://asvs.owasp.org/), [Top 10 A10](https://top10.owasp.org/2025/) | Automatic |
| SEC-12 | Uploads are checked by size and real type | [ASVS V5](https://asvs.owasp.org/), [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Automatic |
| SEC-14 | Text is never run as code: no `eval`, `new Function` or `exec`, and the browser refuses them | [CWE-95](https://cwe.mitre.org/data/definitions/95.html), [CSP 3](https://www.w3.org/TR/CSP3/), [htmx security](https://htmx.org/essays/web-security-basics-with-htmx/) | Automatic |
| SEC-15 | A spreadsheet never runs what it exports: text that could start a formula is neutralised, and no cell holds one | [OWASP CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection) | Automatic |
| SEC-16 | An illustration is a file in `app/ui/static/illustrations/`, shown with `<img>` or as a CSS background, never inline, so nothing in it can run in the page. It and every other SVG shown as an image hold no script, event attribute, `javascript:` address, `<foreignObject>`, or reference outside the file other than an embedded raster image | [SVG Integration, secure animated mode](https://www.w3.org/TR/svg-integration/#secure-animated-mode), [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) | Automatic |
| SEC-17 | An application is exported as files whole or not at all, and the exporter refuses what it can see needs a server: a route that declares a change, a parameter in its address, the database, a form, the query, a header, a cookie or a role's permission, and a page whose HTML holds a form to send, an htmx request or connection, an address loaded from the server, a link to a page that is not there, a missing file or a link among the files it copies. What a route reads without declaring it and what a page's scripts do are not seen: [what it cannot see](../a-static-application.md#what-it-refuses) | Project decision | Automatic |
| SEC-13 | Cookies are `HttpOnly` and `SameSite`, and `Secure` in production; a redirect never leaves the application | [ASVS V3](https://asvs.owasp.org/), [Top 10 A01](https://top10.owasp.org/2025/) | Automatic |
