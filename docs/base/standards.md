---
type: reference
title: Standards
description: "Every rule that screens and components follow, each with its official source and how it is checked: accessibility, usability, language, components, data and security."
tags: [accessibility, usability, i18n, data, security, standards]
related: [specification.md, decisions.md]
---

# Standards

These pages are the single home of the rules, one family a page; this one is their index. Each one has an identifier, a source and a check, so quality does not depend
on anyone's opinion, an AI assistant's included. Tests name the rule they prove with `@pytest.mark.rule("A11Y-05")`.
`tests/test_standards.py` reads those marks from pytest's collection, so a comment or a string does not count. It fails
if a rule has no source, if a rule marked *Automatic* has no test, if a test names a rule that is not *Automatic*, or if
a row starting `| XXX-NN |` does not parse. Rules proved only on demo screens are listed in `tools/remove_demo.py` as
`ONLY_ON_DEMO`, and become *By hand* in a clone.

## Where the rules come from

| Area | Authority | What it is | Access |
|---|---|---|---|
| Accessibility | [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | W3C Recommendation | Free |
| Accessibility | [EN 301 549](https://www.etsi.org/deliver/etsi_en/301500_301599/301549/) | European standard for accessible ICT, published by ETSI | Free |
| Accessibility | [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) | W3C guidance for interactive patterns | Free |
| Usability | [GOV.UK Design System](https://design-system.service.gov.uk/) | Patterns researched with real users, by a government | Free; not a standard |
| Usability | [Nielsen's 10 heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) | The most cited usability reference | Free; not a standard |
| Language | [W3C Internationalization](https://www.w3.org/International/techniques/authoring-html) | W3C guidance for authoring pages | Free |
| Language | [BCP 47](https://www.rfc-editor.org/info/bcp47) | Internet standard for language tags | Free |
| Language | [Unicode CLDR](https://cldr.unicode.org/) | The reference data for formats and plurals | Free |
| Language | [GNU gettext manual](https://www.gnu.org/software/gettext/manual/gettext.html) | The reference for message catalogues | Free |
| Data | [PostgreSQL](https://www.postgresql.org/docs/current/) and [SQLite](https://www.sqlite.org/docs.html) documentation | What each database promises | Free |
| Security | [OWASP ASVS 5.0](https://asvs.owasp.org/) | Verification standard for applications | Free |
| Security | [OWASP Top 10:2025](https://top10.owasp.org/2025/) | The reference list of web risks | Free |
| Security | [CWE Top 25](https://cwe.mitre.org/top25/) | Most dangerous software weaknesses | Free |
| Supply chain | [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final) and [SLSA](https://slsa.dev/spec/) | Secure development and build integrity | Free |

**Reading the tables.** A rule cites the public source it comes from. *Project decision* means no source requires it:
it is a choice of this repository, stated as such, and an organization may change it.

**Usability has no free, testable standard like WCAG.** The international standards exist,
[ISO 9241-110](https://www.iso.org/standard/75258.html) and [ISO 9241-210](https://www.iso.org/standard/77520.html),
but their text is sold, and **this repository does not use them**: nobody here has read them, and no rule rests on them.

**Check** says how a rule is verified: *Automatic* (a test proves the rule as written), *By hand* (in the pull request),
or the milestone that brings it.

To add a rule: find its source first, give it the next identifier, and add its test in the same change.

## Accessibility

[Accessibility](standards/accessibility.md): The accessibility rules, WCAG 2.2 level AA: each with its source and check, the scan and the pass by hand, and how the official examples are treated.

## Usability

[Usability](standards/usability.md): The usability rules screens follow, each with its official source and how it is checked.

## Language

[Language](standards/language.md): The language rules: how a language is chosen and checked, and how texts, numbers and dates follow it, each with its source and check.

## Components

[Components](standards/components.md): The rules components follow, each with its source and check.

## Data

[Data](standards/data.md): The rules that hold for data on both databases, each with its source and check.

## Security

[Security](standards/security.md): The security rules applications inherit, each with its official source and how it is checked.
