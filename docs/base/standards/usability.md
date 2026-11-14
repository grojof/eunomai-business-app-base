---
type: reference
title: "Standards: Usability"
description: "The usability rules screens follow, each with its official source and how it is checked."
tags: [usability, standards]
---

# Usability

| ID | Rule | Source | Check |
|---|---|---|---|
| USE-01 | Each screen designs its loading, empty, error, partial and no-permission states | [Nielsen 1: visibility of system status](https://www.nngroup.com/articles/ten-usability-heuristics/) | By hand |
| USE-02 | Messages say what happened and what to do, in plain language | [Nielsen 9: recover from errors](https://www.nngroup.com/articles/ten-usability-heuristics/), [GOV.UK error message](https://design-system.service.gov.uk/components/error-message/) | By hand |
| USE-03 | A failed submission keeps what was typed | [GOV.UK validation](https://design-system.service.gov.uk/patterns/validation/) | Automatic |
| USE-04 | Actions can be undone where possible; a confirmation names what will be lost | [Nielsen 3 and 5: user control, error prevention](https://www.nngroup.com/articles/ten-usability-heuristics/) | Automatic |
| USE-05 | Filters, sort and page live in the URL, survive a reload and work with the back button | Project decision | Automatic |
| USE-06 | Any action responds at once; a long task shows progress and can be left running | [Nielsen 1: visibility of system status](https://www.nngroup.com/articles/ten-usability-heuristics/) | Milestone 5 |
| USE-07 | One primary action per screen | Project decision | By hand |
| USE-08 | The same thing looks and behaves the same, in the same place | [WCAG 3.2.3](https://www.w3.org/TR/WCAG22/#consistent-navigation), [3.2.4](https://www.w3.org/TR/WCAG22/#consistent-identification), [Nielsen 4: consistency](https://www.nngroup.com/articles/ten-usability-heuristics/) | By hand |
| USE-10 | Every milestone is looked at by a person, in both themes, at desktop and phone width, before it is merged: passing the checks says nothing about how it looks | Project decision | By hand |
| USE-09 | The theme follows the system; a person's choice is remembered | [Media Queries 5](https://www.w3.org/TR/mediaqueries-5/) | Automatic |
