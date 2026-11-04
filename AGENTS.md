# AGENTS.md

## What this project is

A proof of concept for a Series C fintech (~60 engineers) evaluating whether to replace
Microsoft Power Apps with internal tools their own team builds and maintains using Devin.
They run a KYC review queue, a refunds dashboard, and a feature-flag panel in Power Apps
today, and plan to build 10+ more internal tools.

The goal is to show one thing: a small shared platform (`core/`) provides the controls
auditors care about (auth, permissions, audit, four-eyes approvals), so each new internal
tool only has to implement its own business logic.

This is an MVP, not production software. Optimize for clarity and correctness of the core
controls, not for completeness, polish, or scale.

## Where instructions live

- `AGENTS.md` (this file): rules for every session.
- `specs/*.md`: the requirements for a specific task. The spec named in the prompt is the
  source of truth for that session. Build what it says, nothing more.
- `.agents/skills/`: reusable procedures (e.g. adding a new internal tool).

## Stack and commands

- Python 3.11+, FastAPI, Jinja2 server-rendered templates, SQLAlchemy + SQLite, pytest.
- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Seed: `python seed.py`
- Run: `uvicorn main:app --reload`
- Test: `pytest` (all), `pytest core` (platform only), `pytest apps/<tool>` (one tool)

## Architecture rules

- `core/` is the shared platform. `apps/<tool>/` are internal tools built on it.
- Dependencies point one way: apps import from `core/`; `core/` never imports from `apps/`.
- Apps never import from other apps.
- Every route that reads or changes data uses `require_permission(...)`. Deny by default.
- Code checks permissions, never role names. Roles live only in `config/roles.py`.
- Every data change is written with `audit.log(...)`. Never write data without auditing it.
- Actions that need a second person go through `core/approvals`. The approver can never
  be the requester.
- Never write custom auth, permission checks, or audit logic inside an app.
- Add to `core/` only generic mechanisms any app could use, with no tool-specific names
  or rules. Business rules stay in the app. Do not abstract for hypothetical future reuse.

## MVP scope discipline

- Build only what the current spec asks for. If something seems useful but is not in the
  spec, leave it out and list it in the PR description.
- Do NOT add: Docker, Postgres, migrations tooling, CI, deployment config, JS frameworks,
  extra API layers, logging/monitoring, or new dependencies not needed by the spec.
- Prefer the simplest working solution. Readable code beats clever code.
- Use only fake seed data. Never use real names, SSNs, or other real personal data.

## Testing

- Core tests live in `core/tests/` and must not import from `apps/`.
- Each tool's tests live in `apps/<tool>/tests/` and cover only that tool's rules.
- Use the shared fixtures in the root `conftest.py`.
- Run the full test suite before opening a PR. All tests must pass.

## Workflow

- Work on a new branch. Never push to `main`. Open a PR when done.
- Before opening the PR, run the app and manually check the main flow described in the spec.
- PR description must include:
  1. **Summary**: what was built and how it is structured.
  2. **Changes to `core/`**: listed separately, or "None".
  3. **Deliberately left out**: anything skipped or deferred.
  4. **How to verify**: commands and the click-through steps, with screenshots.

## When unsure

Choose the simpler option, state the assumption in the PR description, and keep going.
Ask only if the spec is contradictory or a choice would be hard to undo.
