---
type: reference
title: Excel
description: "How to export a list to Excel with its filters and order, row by row, for large lists"
tags: [base, data, excel]
---

# Excel

`app/core/excel.py` writes a list with XlsxWriter's `constant_memory`, so a row goes to disk as it arrives, and the route
reads the database in blocks with `ListView.everything`. A file exports exactly the address's filters and order.

```python
columns = (ExcelColumn(_("Code")), ExcelColumn(_("Cost"), "number"), ExcelColumn(_("Next inspection"), "date"))
return excel_response(_("Equipment"), columns, rows, settings.time_zone)
```

| What | How |
|---|---|
| Numbers | Rounded by the application's rule, half up, to the column's decimals, because Excel keeps 15 significant digits. A value still too long goes as right-aligned text, every digit there |
| Dates and moments | Real date cells in Excel's own short format, so they read as the computer that opens the file writes them. A moment is shown in the application's time zone. Excel's calendar starts in 1900, so anything earlier goes as text |
| Text | Always text, so a long code keeps its zeros. What could start a formula begins with an apostrophe: see [SEC-15](../standards.md#security). A cell holds 32,767 characters: longer text is cut, ends in an ellipsis and leaves a line in the log, with the row and not the text |
| Language | Headers, the sheet's name, the file's name and labels are the person's, and the date in the file's name is the application's day |
| Too many rows | More than Excel holds is an error, never a shorter file |

The file is written to a temporary file that the system deletes when it closes, and that has no name on disk where the system allows that. The response closes it however the download ends, so a client that leaves, a send that fails or a server that stops leaves it behind nowhere. A background task would not: it runs only after a response that finished. While a file is being written, `constant_memory` keeps XlsxWriter's own temporary file under a name, in the system's temporary folder: a failed row clears it, and only a server killed in those seconds could leave it there.

It runs in a worker thread, so other requests go on. Nobody sees progress: at 50,000 rows it takes about 2.2 seconds on one
laptop before the download starts. Progress belongs to [milestone 5](../milestones.md#milestones).
