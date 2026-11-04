# Internal Tools Platform (`core/`)

Shared foundation that every internal tool must use. Lives in `core/` (not `platform/`,
which would shadow Python's standard library module).

This is a proof of concept, not production. Build only what is specified here.

## Stack & constraints

- Python 3.11+, FastAPI, Jinja2 server-rendered templates, SQLAlchemy with SQLite, pytest.
- Minimal CSS (one stylesheet or a classless CSS file). No JavaScript frameworks.
- Setup and run:
  - `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
  - `python seed.py`
  - `uvicorn main:app --reload`
- Do NOT add: Docker, Postgres, Alembic migrations, CI, deployment config, a separate
  frontend, an API layer beyond the FastAPI routes, logging/monitoring.
- Keep it minimal. If unsure whether something is needed, leave it out and list it in the PR.

## Project layout

- `main.py`: creates the app, adds session middleware, mounts core routes and each tool's routes.
- `core/`: `db.py`, `auth.py`, `permissions.py`, `audit.py`, `approvals.py`, core routes and templates.
- `config/roles.py`: role → list of permissions.
- `apps/<tool>/`: each internal tool (`routes.py`, `models.py`, `permissions.py`, `seed.py`, `templates/`, `tests/`).
- `core/tests/`: tests for the platform only.
- `conftest.py` (repo root): shared fixtures — a fresh SQLite test database per test, a
  TestClient, and a helper to create a user with given roles and log them in.
- `pytest.ini`: test paths `core/tests` and `apps`.
- `seed.py` (runs core seed, then each tool's seed), `requirements.txt`, `README.md`.

## Test structure

- Core tests live in `core/tests/` and must NOT import anything from `apps/`. They use a
  small test-only route and permission defined inside the test files, so the platform is
  proven to work with no apps installed.
- Each app's tests live in `apps/<tool>/tests/` and cover only that app's business rules.
  They use the shared fixtures and do not re-test core behavior.
- `pytest` runs everything; `pytest core` runs platform tests only; `pytest apps/kyc` runs
  one app's tests.

## Auth

- Real login: `/login` form with username + password, checked against bcrypt hashes in the
  users table. Never store plaintext passwords.
- On success, store the user id in a signed session cookie (Starlette `SessionMiddleware`).
  Secret key from the `SESSION_SECRET` env var, with a dev default.
- `/logout` clears the session.
- Every route except `/login` requires authentication. Unauthenticated requests redirect to `/login`.
- `get_current_user` (a FastAPI dependency) is the ONLY place the app determines who the
  user is, so a real OIDC provider (Okta/Entra) can replace it later without changing app code.
- Successful and failed logins are written to the audit log.
- Seeded users share one demo password, documented in the README.
- The page header shows the logged-in user, their roles, and a logout button.

## Permissions

- `core/` defines NO app-specific roles or permissions. Its only own permission is `core:audit.view`.
- Each app declares its permissions in `apps/<tool>/permissions.py`, namespaced as
  `<app>:<resource>.<action>`.
- Roles live in `config/roles.py`: role → list of permissions. Roles are scoped to one app
  (or to core), e.g. `kyc_analyst`, `support_lead`, `auditor`. No combined cross-app roles.
- A user can have multiple roles (stored in a `user_roles` table). Effective permissions are
  the union of all the user's roles' permissions.
- `require_permission(permission)`: a FastAPI dependency enforced server-side on every route
  that reads or changes data. Deny by default; return 403.
- App code checks permissions, never role names.

## Audit log

- `audit.log(actor, action, entity_type, entity_id, before=None, after=None, reason=None)`
- Stored fields: id, timestamp, actor id, action, entity type, entity id, before (JSON),
  after (JSON), reason.
- Append-only: the audit module exposes no update or delete functions.
- `/audit` page (requires `core:audit.view`): a simple table of entries, newest first.

## Approvals (four-eyes)

- `approvals.request(actor, type, entity_type, entity_id, payload, approver_permission)`
  creates a PENDING approval request.
- `approvals.decide(actor, approval_id, decision, reason)` sets APPROVED or REJECTED.
  - The actor must have the request's `approver_permission`.
  - The actor must NOT be the user who made the request.
  - It returns the decided request; the calling app applies the outcome to its own entity
    in the same database transaction.
- Every request and decision is written to the audit log.

## Home page

- `/` lists the tools the logged-in user can access.
- Each app registers its name, URL, and the permission required to see it.

## Core seed data

- Roles in `config/roles.py`: `auditor` with `core:audit.view`.
- User: `audrey` (auditor).

## Tests (required, in `core/tests/`, pytest with FastAPI TestClient)

- Login with a wrong password fails; the correct password succeeds and sets a session.
- An unauthenticated request to a protected page redirects to `/login`.
- A user without the required permission gets 403 on a protected route.
- A user with two roles has the union of both roles' permissions.
- The audit module has no update or delete functions; entries can only be added.
- A requester cannot approve their own approval request.
- A user without the approver permission cannot decide an approval request.

## Done when

`pytest core` passes, the app runs with the commands above, and `README.md` explains setup,
the demo users, and the demo password.

## Out of scope (list in the README as production gaps)

CSRF protection, login rate limiting and lockout, static separation of duties
(forbidding conflicting role combinations), roles sourced from IdP groups, MFA, SSO via OIDC, secure cookie settings
behind HTTPS, database-level enforcement of append-only audit, field-level PII masking.
