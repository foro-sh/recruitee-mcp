# AGENTS.md

A FastMCP server for Recruitee that deploys to foro.sh. README.md covers the tools, setup and
which API assumptions are still unverified.

## Commands

- `uv run pytest` runs the tests.
- `uv run ruff format . && uv run ruff check .` formats and lints.

## Working here

- Re-lock after every dependency change (`uv add` / `uv remove`, or `uv lock`), and commit `uv.lock`.
  Deploys install from the lockfile as-is.
- Tools live in `recruitee_mcp/tools/`, one module per area, each registered via `register(tool, get_client)`.
  Use `@tool()` for reads and `@tool(writes=True, ...)` for writes, so the annotations stay right.
- Every path, parameter and body comes from https://apidocs.recruitee.com or a response actually seen.
  When you rely on something the docs don't state, add it to the README's "Still to check" list.
- Tool names are a contract with foro's Bridge catalog (`apps/web/lib/bridge-catalog.ts` in
  foro-sh/platform). Renaming or removing one is a breaking release.
- Secrets come from the environment: `RECRUITEE_COMPANY_ID`, `RECRUITEE_API_TOKEN` and optionally
  `RECRUITEE_TIMEZONE`. Never commit them.
