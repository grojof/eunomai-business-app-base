# Third-party notices

The files below are copied into this repository, pinned by version and hash in `vendor.json`. Each keeps its own
licence; the base's own code is under the [MIT licence](LICENSE). Python packages are not copied: `uv.lock` pins
them, and each is installed with its own licence.

| Component | Version | Where | Licence |
|---|---|---|---|
| [htmx](https://github.com/bigskysoftware/htmx) | 2.0.11 | `app/ui/static/vendor/htmx.min.js` | Zero-Clause BSD |
| [Chart.js](https://github.com/chartjs/Chart.js) | 4.5.1 | `app/ui/static/vendor/chart.umd.min.js` | MIT, (c) 2025 Chart.js Contributors |
| [SortableJS](https://github.com/SortableJS/Sortable) | 1.15.7 | `app/ui/static/vendor/Sortable.min.js` | MIT, Copyright (c) 2019 All contributors to Sortable |
| [FullCalendar](https://github.com/fullcalendar/fullcalendar) | 7.1.3 | `app/ui/static/vendor/fullcalendar*.js`, `fullcalendar*.css` | MIT, Copyright (c) 2026 Adam Shaw |
| [Lucide](https://github.com/lucide-icons/lucide) (`lucide-static`) | 1.63.0 | `app/ui/templates/ui/icons/`, `tools/lucide/index.json` | ISC, Copyright (c) 2026 Lucide Icons and Contributors, with the MIT notice of the icons derived from Feather: in `app/ui/templates/ui/icons/LICENSE` |
| [daisyUI](https://github.com/saadeghi/daisyui) | 5.7.50 | `tools/tailwind/daisyui*.mjs`, `daisyui-docs.json`, `daisyui-llms.txt`, `app/demo/examples/` | MIT, Copyright (c) 2020 Pouya Saadeghi: in `app/demo/examples/LICENSE.daisyui` |
| [axe-core](https://github.com/dequelabs/axe-core) | 4.14.0 | `tests/vendor/axe.min.js` (tests only) | Mozilla Public License 2.0, Copyright (c) 2015 - 2026 Deque Systems, Inc., its notice in the file |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) standalone executable | 4.3.3 | Downloaded by `tools/css.py` into `.cache/`, not committed | MIT |

The MIT licence's text, which the components above under MIT share:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
> documentation files (the "Software"), to deal in the Software without restriction, including without limitation
> the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright
> notice and this permission notice shall be included in all copies or substantial portions of the Software. THE
> SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.
