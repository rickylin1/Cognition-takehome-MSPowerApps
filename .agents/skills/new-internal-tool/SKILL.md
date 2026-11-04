---
name: new-internal-tool
description: Add a new internal tool under apps/<tool>/ on the shared core/ platform (auth, permissions, audit log, four-eyes approvals), from a spec in specs/. Use when asked to build, add, or scaffold an internal tool in this repo.
---

# Add a new internal tool

Reference implementation: `apps/kyc/`. Copy its structure, not its business rules.

## Inputs needed
- The spec file for the new tool, `specs/<tool>.md`. It is the source of truth; build only what it says.

## Procedure
1. Read `AGENTS.md`, `specs/platform.md`, the tool's spec, and skim `core/` and `apps/kyc/`; reply with a short plan, then proceed.
2. Create a new branch. Run the full setup from `AGENTS.md` (create the venv if missing, install requirements).
3. Create `apps/<tool>/` with `__init__.py`, `permissions.py`, `models.py`, `routes.py`, `seed.py`, `templates/`, `tests/__init__.py`.
4. Declare every permission as a constant in `apps/<tool>/permissions.py`, named `<tool>:<resource>.<action>`.
5. Add the spec's roles to `config/roles.py`, each scoped to this tool only (no cross-app roles).
6. Define SQLAlchemy models on `core.db.Base` in `models.py`, with table names prefixed `<tool>_`.
7. Put every state change in a `models.py` function taking `(db, actor, entity, ...)` that validates, mutates, calls `audit.log(...)`, and does not commit.
8. Audit every change with before/after state and reason. Also audit views of sensitive personal data — government IDs, SSNs, dates of birth, full card or bank account numbers — with action `<tool>.<entity>.viewed`. Names, amounts, and statuses alone are not sensitive.
9. Route four-eyes actions through `approvals.request(...)` with the approver permission, and `approvals.decide(...)` before applying the outcome to your entity.
10. If the spec needs something `core/` doesn't provide:
    - Controls (auth, permissions, audit, approvals, sensitive-data handling): add a generic version to `core/` with tests in `core/tests/`. Never implement a control inside the tool.
    - Anything else: implement it inside the tool. If similar logic already exists in another app, do NOT import it or move it to `core/`; list it in the PR under 'Candidates for `core/`', naming where it's duplicated.
    - Never refactor other apps as part of building this tool.
11. Protect every route in `routes.py` with `Depends(require_permission(<PERMISSION>))`, including GET pages; use `APIRouter(prefix="/<tool>")`.
12. In routes, call the model function, `db.commit()` on success (303 redirect), and on the app's error `db.rollback()` and re-render with status 400.
13. Register the tool on the home page in `routes.py`: `register_tool("<Name>", "/<tool>", <VIEW_PERMISSION>)`.
14. Mount the router in `main.py` (`app.include_router(...)`).
15. Write `apps/<tool>/seed.py: run(db)` creating users via `core.auth.create_user(db, name, DEMO_PASSWORD, roles)` and fake records; append it to `SEEDS` in root `seed.py`.
16. Add the new demo users and roles to the README demo-users table.
17. Write tests in `apps/<tool>/tests/` covering every rule listed in the spec, using root `conftest.py` fixtures; test only this tool's rules.
18. Run `pytest core`, `pytest apps/<tool>`, then `pytest`; fix until all pass.
19. Run `python seed.py && uvicorn main:app --reload`, log in as the seeded users, click through the spec's main flow, check `/audit` as `audrey`, and take screenshots.
20. Open a PR with sections Summary, Changes to `core/` (or "None"), Candidates for `core/` (or "None"), Deliberately left out, How to verify (commands, click-through steps, screenshots).

## Specifications
- `pytest core` and `pytest apps/<tool>` pass (and `pytest` overall).
- Every route under `/<tool>` returns 403 for a user lacking its permission and redirects to `/login` when logged out.
- Every data change (and sensitive read) creates an `AuditEntry`; four-eyes actions cannot be approved by the requester.
- The tool appears on `/` only for users with its view permission; `python seed.py` loads its fake data.
- No app code mentions role names; roles exist only in `config/roles.py`.
- Every spec rule has a test, and the spec's main flow works in the running app.

## Advice
- Reuse, don't rewrite: `require_permission` / `has_permission` (`core.permissions`), `get_current_user` (`core.auth`), `audit.log`, `approvals.request` / `approvals.decide`, `register_tool`, `get_db`, `create_user`, `DEMO_PASSWORD` (`core.seed`).
- `audit.log`, `approvals.request` and `approvals.decide` take `db` first and only flush, so entity change, audit entry and approval commit together in the route.
- `approvals.decide` already enforces the approver permission and requester != approver by raising `PermissionDenied` (main.py turns it into 403); don't re-check it.
- Use `has_permission(user, ...)` only to show or hide UI sections; the route still needs `require_permission`.
- Raise `HTTPException(404)` for missing records; define one app error class (subclass per rule) that routes show to the user.
- Templates: `Jinja2Templates(directory=[apps/<tool>/templates, core/templates])`, extend `base.html` (blocks `title`, `content`) and pass `user` in the context.
- Snapshot state with a small `_state(entity)` dict helper for audit `before`/`after`; name actions `<tool>.<entity>.<verb>`, entity_type `<tool>_<entity>`.
- Test rules by calling model functions with the `db` and `create_user(name, roles)` fixtures; add one route-level flow test with `client` (no auto-redirects) and `login_as`.
- For test-only roles, `monkeypatch.setitem(config.roles.ROLES, ...)`; `create_user` rejects roles not in `ROLES`.
- Seed data must be obviously fake (invented names, SSNs in the never-issued 9xx range).
- Keep FastAPI `/docs`, `/redoc`, `/openapi.json` disabled in `main.py`; they bypass auth.

## Forbidden actions
- Custom auth, session, permission, or role-name checks inside `apps/<tool>/`.
- Any route without `require_permission`, or writing data without `audit.log`.
- Updating or deleting audit entries, or a four-eyes flow that bypasses `core/approvals`.
- Importing from another app, or importing `apps/` from `core/`.
- Changing `core/` without listing each change under "Changes to `core/`" in the PR; adding tool-specific names or rules to `core/`.
- Real personal data, new dependencies, Docker/Postgres/migrations/CI/JS frameworks, or features not in the spec.
- Pushing to `main`, or opening the PR with failing tests.
