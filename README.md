# Cognition-takehome-MSPowerApps

Proof of concept: a small shared platform (`core/`) that gives every internal tool the
controls auditors care about (authentication, permissions, an append-only audit log, and
four-eyes approvals), so each tool in `apps/<tool>/` only implements its own business logic.
See `AGENTS.md` for project rules and `specs/` for task specs.

## Background

A Series C fintech (~60 engineers) runs several internal operations tools in Microsoft
Power Apps today: a KYC review queue, a refunds dashboard, and a feature-flag panel. It
plans to build 10+ more.

The approach:

1. **Build the controls once, in `core/`** (`specs/platform.md`): login, deny-by-default
   permissions, an append-only audit log, and four-eyes approvals.
2. **Build each tool from a short spec** (`specs/<tool>.md`) that describes only the
   business rules: data, permissions, roles, screens, statuses, and tests.
3. **Measure the result**: each tool should need no new auth, permission, or audit code of
   its own, and ideally no changes to `core/` at all.

Two Power Apps tools have been rebuilt this way so far: the [KYC review queue](#kyc-review-queue-appskyc)
and the [refunds dashboard](#refunds-dashboard-appsrefunds). Both were built on the
unchanged `core/` platform. The refunds dashboard was the second tool and was built by
following the reusable procedure in `.agents/skills/new-internal-tool/SKILL.md`, which was
written from the KYC build so later tools follow the same conventions.

The third Power Apps tool, the feature-flag panel, was deliberately not rebuilt:

- **Two tools were enough to prove the point.** The second tool (refunds) reused `core/`
  without any changes, so a third would add little new evidence.
- **It tells auditors less.** The feature-flag panel doesn't touch customer PII or move
  money, so it exercises the controls less than KYC and refunds do.
- **This is a time-boxed PoC.** The panel is deferred, and it is the natural next tool to
  build from a spec.

## How the platform works

Every tool gets these controls from `core/` instead of writing its own:

| Control | How a tool uses it | What it guarantees |
|---|---|---|
| Authentication | `get_current_user` (`core/auth.py`) | Every route except `/login` requires a session; logged-out users are redirected to `/login`. |
| Permissions | `Depends(require_permission("<tool>:<resource>.<action>"))` on every route | Deny by default. Code checks permissions, never role names; roles map to permissions only in `config/roles.py`. A user's effective permissions are the union of their roles. Missing permission returns 403. |
| Audit log | `audit.log(db, actor, action, entity_type, entity_id, before, after, reason)` | Every data change records who, what, before/after state, and why. Entries are append-only and viewable at `/audit` with `core:audit.view`. Logins (including failed ones) are also audited. |
| Four-eyes approvals | `approvals.request(...)` then `approvals.decide(...)` | The approver must hold the required permission and can never be the requester. |
| Home page | `register_tool(name, url, permission)` | Users only see tiles for tools they can open. |

The audit entry, the approval record, and the tool's own data change are written in the
same database transaction, so a change is never saved without its audit trail.

## Setup and run

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python seed.py            # resets app.db and loads fake demo data
uvicorn main:app --reload # http://127.0.0.1:8000
```

Optional environment variables: `SESSION_SECRET` (session cookie signing key; a dev default
is used if unset), `DATABASE_URL` (default `sqlite:///./app.db`).

## Demo users

All seeded users share the demo password **`demo-password`**.

| User     | Roles     | Can do                  |
|----------|-----------|-------------------------|
| `audrey` | `auditor` | View the audit log (`/audit`) |
| `alice`, `carol` | `kyc_analyst` | View and decide KYC cases (`/kyc`) |
| `bob` | `kyc_senior_analyst` | Also give the second review on watchlist cases |
| `frank` | `kyc_analyst` + `auditor` | KYC analyst who can also view the audit log (two roles) |
| `dana` | `support_agent` | View transactions and request refunds (`/refunds`) |
| `erin` | `support_lead` | Also approve refunds above the $500 threshold |

## Tests

```bash
pytest            # everything
pytest core       # platform only
pytest apps/<tool> # one tool
```

## Layout

- `main.py`: creates the app, adds session middleware, mounts core and tool routes.
- `config/roles.py`: role -> permissions (the only place role names appear).
- `core/db.py`: SQLAlchemy engine, session, `get_db`.
- `core/auth.py`: users, bcrypt passwords, `get_current_user` (the single place the user is identified).
- `core/permissions.py`: `require_permission(...)` dependency; effective permissions are the union of the user's roles.
- `core/audit.py`: `audit.log(db, actor, action, entity_type, entity_id, before, after, reason)`; append-only.
- `core/approvals.py`: `approvals.request(...)` / `approvals.decide(...)`; the approver can never be the requester.
- `core/registry.py`: `register_tool(name, url, permission)` for the home page.
- `core/routes.py`, `core/templates/`: `/login`, `/logout`, `/`, `/audit`.
- `apps/<tool>/`: internal tools built on `core/`.
- `apps/kyc/`: KYC review queue (`specs/kyc.md`). Cases with a watchlist hit need a second
  review from a different `kyc_senior_analyst` via `core/approvals`.
- `apps/refunds/`: refunds dashboard (`specs/refunds.md`). Refunds above the threshold in
  `config/refunds.py` ($500) need approval from a different `support_lead` via `core/approvals`.

## The internal tools

Roles and seed users for both tools are in [Demo users](#demo-users).

### KYC review queue (`apps/kyc`)

Compliance analysts review applicant KYC cases (10 fake cases with mock document, identity,
and watchlist check results) at `/kyc`. Spec: `specs/kyc.md`.

- A case with no watchlist hit is approved or rejected directly by one analyst.
- A case with a watchlist hit needs four-eyes review. The analyst's decision becomes a
  proposal (`PENDING_SECOND_REVIEW`) via `core/approvals`, and a different
  `kyc_senior_analyst` makes the final decision.
- Every decision requires a reason and is audited with before/after status.

**Try it:** log in as `alice` and decide a watchlist case. Log in as `bob` and give the
second review. Log in as `audrey` and check `/audit`.

### Refunds dashboard (`apps/refunds`)

Support staff refund customer transactions (10 fake transactions) at `/refunds`. Payments
are mocked: issuing a refund only records it. Spec: `specs/refunds.md`.

- A refund can't exceed the transaction amount minus refunds already issued.
- Refunds up to $500 (`APPROVAL_THRESHOLD` in `config/refunds.py`) are issued immediately.
- Larger refunds wait in `/refunds/approvals` until a different `support_lead` approves or
  rejects them via `core/approvals`.
- Every request, approval, rejection, and issuance is audited.

**Try it:** log in as `dana` and request a $700 refund. Log in as `erin` and approve it.
Log in as `audrey` and check `/audit`.

Both tools use the same `core/approvals` for different triggers (a watchlist hit vs. a
dollar threshold), and neither needed changes to `core/` or any custom auth, permission,
or audit code.

## Adding another tool

Write `specs/<tool>.md` (see the existing specs for the format) and build it by following
`.agents/skills/new-internal-tool/SKILL.md`.

## Production gaps (out of scope for this PoC)

- CSRF protection
- Login rate limiting and account lockout
- Static separation of duties (forbidding conflicting role combinations)
- Roles sourced from IdP groups
- MFA
- SSO via OIDC (Okta/Entra) — would replace `get_current_user`
- Secure cookie settings behind HTTPS
- Database-level enforcement of the append-only audit log
- Field-level PII masking
