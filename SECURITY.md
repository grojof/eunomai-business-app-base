# Security policy

eunomai-business-app-base is a base for internal web applications: an organization makes its template from it, and each application starts from that template. It trusts a reverse proxy for identity and has no login of its own; see [Identity](docs/base/specification.md#identity) and [Standards](docs/base/standards.md).

## Supported versions

Pre-1.0: only the newest release, and `main`, receive security fixes. Reproduce on the current `main` before
reporting.

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Use GitHub's private vulnerability reporting: the
repository's *Security* tab, *Report a vulnerability*. Include the affected part, the version or commit, a minimal
reproduction and the impact you saw. A report is acknowledged within a few working days and kept up to date until
it is fixed and disclosed.

## Scope

In scope: the application's core (`app/core/`), its components and templates (`app/ui/`), and the tools (`tools/`). Out of scope: the vendored libraries listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), the Python packages in `uv.lock`, and the proxy, database and server an organization runs it with: report those to their own projects.
