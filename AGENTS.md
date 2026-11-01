## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default five-label triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Use a single-context domain documentation layout. See `docs/agents/domain.md`.

## Live Monitor API

- OpenAPI contract: `docs/api/live-monitor-openapi.json`.
- Runtime configuration is loaded from the repository-root `.env` file.
- Base URL environment variable: `LIVE_MONITOR_BASE_URL`.
- Authentication token environment variable: `LIVE_MONITOR_API_TOKEN`.
- Never print, log, hard-code, or commit values from `.env`.
- Send authentication as `Authorization: Bearer <token>`.
- Before modifying the integration, read the OpenAPI contract.

## Python coding style

- Follow the Google Python Style Guide for new and modified Python code.
- Add parameter and return type annotations, including async functions and tests.
- Prefer precise types, TypedDict, and Protocol over Any; document untyped library boundaries.
- Use Google-style docstrings for public interfaces and nontrivial behavior.
- Use module imports, four-space indentation, and an 80-character line limit.
- Format with YAPF using `.style.yapf`; verify types and run relevant tests.
- Do not reformat unrelated legacy code as part of a feature change.
