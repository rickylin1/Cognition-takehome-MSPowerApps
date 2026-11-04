# Cognition-takehome-MSPowerApps

Proof of concept: a small shared platform (`core/`) that gives every internal tool the
controls auditors care about (authentication, permissions, an append-only audit log, and
four-eyes approvals), so each tool in `apps/<tool>/` only implements its own business logic.
See `AGENTS.md` for project rules and `specs/` for task specs.

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

The platform seeds only `audrey`, as `specs/platform.md` asks; core has no other roles yet.
Each tool's PR adds its own roles to `config/roles.py` and its users to the seed:

| Tool PR | User | Roles | Can do |
|---------|------|-------|--------|
| KYC (`specs/kyc.md`) | `alice`, `carol` | `kyc_analyst` | View and decide KYC cases |
| KYC | `bob` | `kyc_senior_analyst` | Also give the second review on four-eyes cases |
| KYC | `frank` | `kyc_analyst` + `auditor` | KYC analyst who can also view the audit log (two roles) |
| Refunds (`specs/refunds.md`) | `dana` | `support_agent` | View transactions, request refunds |
| Refunds | `erin` | `support_lead` | Also approve refunds |

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
