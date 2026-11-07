## Project orientation

- Read `docs/project-layout.md` for the current module map and import paths.
- Read `docs/development.md` for setup, validation, and cross-machine handoff.
- `main.py` is the bot entry point; `app.py` is a separate download service.
- Keep command handling in `commands/`, external clients in `integrations/`,
  scheduling in `scheduling/`, and QQ message utilities in `messaging/`.
- Administration lives in `admin/`; live event forwarding lives in
  `live_forwarding/`. Do not recreate the removed root-level modules.
- Run development commands from the repository root. Preserve existing config,
  asset, and database locations when moving modules; add path regression tests.

## Development and validation

- Use Python 3.11 as documented in `requirements.txt`, with a local virtual
  environment. Install runtime dependencies from that file.
- Black and Pyright are separate development tools. Prefer command-line
  checks; Pylance in VS Code provides live diagnostics using the shared
  Pyright configuration. Node.js runs the frontend tests.
- Do not hard-code a developer's Python executable, username, or absolute path
  in project code, scripts, or instructions.
- Default to offline tests. Run the relevant tests during development and the
  full regression suite before handing off code changes:

  ```text
  python -X utf8 -m unittest discover -s tests
  node --test tests/admin_ui.test.cjs
  ```

- Format only changed Python code with Black using `pyproject.toml`; check
  affected modules with `python -m pyright`. Prefer CLI tools over UI
  automation whenever they support the task. Report the scope checked and
  any pre-existing failures accurately; distinguish Pyright CLI results
  from Pylance editor diagnostics.
- Documentation-only edits require link/path and diff checks, not a full test
  run, unless they also change executable configuration or behavior.

## Safety and handoff

- Never print, log, hard-code, or commit secrets, including `.env` values.
  Use `.env.example` for variable names and safe placeholders only.
- Offline development must not require production API keys or databases.
  Do not copy production data into tests or tracked files.
- Do not start a second bot using production credentials: scheduled tasks and
  forwarding may send duplicate messages. Use isolated test configuration.
- Real QQ sends, paid API tests, production database changes, SSH operations,
  deployments, and Git pushes require explicit user authorization for that
  action; code changes alone do not authorize them.
- Inspect the worktree first and preserve unrelated user changes. Prefer small,
  independently reversible commits; never reset or discard user work.
- At handoff, summarize changes, checks, commit IDs, and remaining work. State
  whether changes were pushed or deployed. Keep durable project decisions in
  repository documentation rather than relying on prior chat history.
- User-installed skills and machine-specific settings are not repository
  dependencies. Do not assume paths under another developer's user directory
  exist on a new computer; use repository instructions as the baseline.

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
- Format with Black using `pyproject.toml`; run Pyright and
  relevant tests.
- Do not reformat unrelated legacy code as part of a feature change.
