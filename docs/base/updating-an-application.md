---
type: reference
title: Updating an application
description: "How an application takes a newer template: tools/update_application.py, what it merges and what it keeps"
tags: [base, updating-an-application]
---

# Updating an application

A template carries `tests/base_files.json`, the fingerprint of each file of the base it holds, and an `AGENTS.md` that
describes the application by pointing to its README and its own pages. An update brings both: an application that
changed a file of the base makes `tools/test.py --application` run every test, which costs time and nothing else; one
whose `AGENTS.md` filled in its first section keeps its text, and takes a new paragraph by hand when the update meets
both.

```bash
uv run --frozen python tools/update_application.py --template <template repository> --check
uv run --frozen python tools/update_application.py --template <template repository>
```

`.template-source` says which version of the template an application was made from. The tool finds that version in
the template's history and merges the change from it to the newest (or `--to`) into the application, with git's own
three-way merge and that version as the base. A file the application never touched takes the new version; one it
changed is merged; where both changed the same lines, the file keeps conflict markers for a person. The application's
own files are not touched. `--check` changes nothing and says what would happen: the versions, the template's files
the application changed, and which files would merge cleanly or not. Without it the update goes on a new branch,
`template-<base>`, committed when nothing is in conflict. It never pushes. An application made before the tool
existed runs it from a newer template's folder, with `--application` naming its own. It needs git 2.40 or later (`git merge-tree --merge-base`), as IT's computers have;
without it, it says so and changes nothing, and its tests are skipped: a person's computer has no git on purpose.

An update may change `.python-version`, when the base moves to a newer Python. uv downloads that version the first
time it is needed; where downloads are off (a server, or computers where IT installs Python), IT installs it first
(`uv python install <version>`), and `uv sync --frozen` makes the environment again.

| Decision | Why | Instead of |
|---|---|---|
| The template's change, merged with the version the application came from as base | Exactly what the template changed reaches the application, and what the application changed stays: a file both changed is merged line by line | Copying the template's files over the application, which loses its changes; merging the base, whose demo the application never had |
| A branch, never a push | The application's tests and a person's review decide, through the pull request, as for any change | Updating `main`, or every application at once |
| The version found by `.template-source` in the template's history | A repository made from a template on a git server keeps the files, not the history; `.template-source` is what is left of where it came from | Asking the person which version it was |
