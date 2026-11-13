---
type: reference
title: Uploads
description: "How an attached file is checked and stored: allowed kinds, signatures, sizes and where files live"
tags: [base, data, uploads]
---

# Uploads

`app/core/uploads.py` answers [SEC-12](../standards.md#security). What a file calls itself proves nothing, so a file passes
only if its name is safe and its first bytes say what its extension says.

| What | How |
|---|---|
| The list | PDF, PNG and JPEG, each with its signature, in `KINDS`. A kind needs a signature to join: plain text or CSV has none, and needs a reader of its own. The browser's `accept` helps a person choose and decides nothing |
| Refused | Too big, empty, a type off the list, a renamed extension, a real file under another kind's name, a path or a special character in the name, a name that is blank before its extension, and a double extension. `report.v2.pdf` is refused with them: a rule with no exceptions is one that cannot be got round, and the message says what to do |
| Stored | Under a random name of ours, with no extension and only the application able to read it, in `APP_UPLOAD_FOLDER`. By default that is `.data/uploads`, which git ignores, and a folder inside `app/` stops the application from starting. The folder appears with the first file |
| Sent back | Reached only by the numbers of the order and the file, for the `admin` role, as an attachment, with `nosniff` and never cached. No path is built from anything a person sent: the stored name comes from the database and is checked again |
| Limits | `APP_UPLOAD_MAX_BYTES`, 10 MB, for a file, and `APP_REQUEST_MAX_BYTES`, 32 MB, for any request, on every route, because the framework reads a form to disk before any route runs. A declared length refuses a body early, and every body is counted as it arrives, whatever its headers say. A request with both `Content-Length` and `Transfer-Encoding` is a 400, unread. Between the two, a person gets an error on the field and keeps what was typed. Past the second, a 413: a message with htmx, with the form intact, and a page without JavaScript |
| A failed save | A browser cannot keep a chosen file when a form comes back, so the field says to choose it again. Nothing is stored until the whole form passes |
| Removing | With a confirmation that names it. Deleting an order names the files that go with it. A file leaves the disk after its row, so a failure leaves an untidy file, never a row without one, and the log says so. `app.demo.generate` empties the folder of stored files, because their rows have gone |

**What a clone must add for production.** This is a floor. Each of these depends on where the application lives, so none
is in the base:

| Add | Why |
|---|---|
| Virus scanning, with the file held back until it passes | A real PDF or JPEG can carry something harmful. Signatures say what a file is, not that it is good. Run a scanner such as ClamAV between the upload and the moment anyone can download it |
| A limit at the reverse proxy, below `APP_REQUEST_MAX_BYTES` | It stops a long body before Python sees it, and answers cleanly: an application that answers without reading the body can have its connection reset |
| Storage that fits the deployment | A local folder works on one server. Several servers need a shared volume or an object store, with `UploadStore` behind the same four calls, and a backup that moves together with the database |
| Quotas and a rate limit, per person | Without them one person can fill the disk, 10 MB at a time |
| Reading images again, where they are shown | Files here are only downloaded. An application that shows an image should decode it and write a new one, which drops what was hidden in it, and serve it from another origin |
| A record of who added, downloaded and removed what | The demo keeps a moment and no name. A real application needs its audit trail, under the rules for personal data |
| Retention, and sweeping files with no row | A crash between a file reaching the disk and its row being saved or removed, or a removal that fails, leaves a file behind. Decide how long files stay, and clear them on a schedule |
