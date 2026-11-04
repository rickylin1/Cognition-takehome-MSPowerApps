# Cognition-takehome-MSPowerApps

Proof of concept: a small shared platform (`core/`) that gives every internal tool the
controls auditors care about (authentication, permissions, an append-only audit log, and
four-eyes approvals), so each tool in `apps/<tool>/` only implements its own business logic.
See `AGENTS.md` for project rules and `specs/` for task specs.

## Background

A Series C fintech (~60 engineers) runs several internal operations tools in Microsoft
Power Apps today: a KYC review queue, a refunds dashboard, and a feature-flag panel. It
plans to build 10+ more. The question this repo answers is whether the team can replace
Power Apps with tools it builds and maintains itself (with Devin) without each tool
re-implementing, and getting subtly wrong, the controls compliance depends on.

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

### KYC review queue (`apps/kyc`)

**What it replaces.** The Power Apps screen compliance analysts use to work Know Your
Customer cases. This is only the human review layer: intake, identity-vendor checks, and
automated decisioning happen elsewhere and are represented by seed data. Spec:
`specs/kyc.md`.

**Data.** 10 fake applicant cases, each with name, date of birth, SSN (fake, never-issued
9xx range), address, ID document type, mock check results (document check, identity
match, watchlist hit), status, and timestamps. At least 3 cases have a watchlist hit.

**Who uses it.**

| Role | Permissions | Seed users |
|---|---|---|
| `kyc_analyst` | `kyc:case.view`, `kyc:case.decide` | `alice`, `carol`, `frank` (also `auditor`) |
| `kyc_senior_analyst` | adds `kyc:case.second_review` | `bob` |

**Screens.**

- `/kyc`: the queue, showing each case's applicant, check summary, and status. Senior
  analysts also see an "Awaiting second review" section.
- `/kyc/cases/{id}`: applicant data, check results, and approve/reject buttons with a
  required reason.

**Workflow.**

```
PENDING ──(no watchlist hit: analyst decides)──────────────► APPROVED | REJECTED
PENDING ──(watchlist hit: analyst proposes a decision)─────► PENDING_SECOND_REVIEW
PENDING_SECOND_REVIEW ──(different senior analyst decides)─► APPROVED | REJECTED
```

- A clean case is decided directly by one analyst.
- A watchlist-hit case is the four-eyes case: the analyst's decision becomes a proposal,
  stored as a `core/approvals` request, and the case waits for a second review. A different
  user with `kyc:case.second_review` makes the final decision. The approval is marked
  approved if they agree with the proposal and rejected if they overrule it.
- The analyst who submitted a case can never give its second review.
- Every decision requires a reason. Any other status transition raises an error.

**Audit trail.** `kyc.case.decided`, `kyc.case.submitted_for_second_review`, and
`kyc.case.second_review_decided`, each with before/after status and the reason.

**Out of scope.** Escalation, case assignment, filters, PII masking, intake, vendor
integrations, rules engine, customer information requests, notifications, reporting.

**Try it.** Log in as `alice`, open a watchlist case, and submit a decision. Log in as
`bob`, open it from "Awaiting second review", and decide it. Log in as `audrey` and check
`/audit`.

### Refunds dashboard (`apps/refunds`)

**What it replaces.** The Power Apps screen support staff use to refund customer
transactions. Payment processing is mocked: "issuing" a refund only records it. Spec:
`specs/refunds.md`.

**Data.** 10 fake transactions, each with customer name, amount, date, merchant, and status
(`SETTLED`, `PARTIALLY_REFUNDED`, or `REFUNDED`). Amounts are stored in integer cents.

**Who uses it.**

| Role | Permissions | Seed users |
|---|---|---|
| `support_agent` | `refunds:transaction.view`, `refunds:refund.request` | `dana` |
| `support_lead` | adds `refunds:refund.approve` | `erin` |

**Screens.**

- `/refunds`: the transactions list.
- `/refunds/transactions/{id}`: transaction detail, its refund history, and a refund form
  (amount + reason).
- `/refunds/approvals`: pending refunds awaiting approval, for users with
  `refunds:refund.approve`.

**Workflow.**

```
amount <= $500 ───────────────────────────────► ISSUED (immediately)
amount >  $500 ──► PENDING_APPROVAL ──(different support lead approves)──► ISSUED
                                    └─(different support lead rejects)───► REJECTED
```

- A refund can't exceed the transaction amount minus refunds already issued. This is
  checked again at approval time, in case another refund was issued in the meantime.
- Refunds up to the approval threshold are issued immediately. The threshold is
  `APPROVAL_THRESHOLD = Decimal("500.00")` in `config/refunds.py`, so it can change without
  touching code.
- Refunds above the threshold go through `core/approvals` and need a different user with
  `refunds:refund.approve`. The requester can never approve their own refund.
- When a refund is issued, the transaction moves to `PARTIALLY_REFUNDED` or `REFUNDED`.
- Every request and decision requires a reason.

**Audit trail.** `refunds.refund.requested`, `refunds.refund.approved`,
`refunds.refund.rejected`, `refunds.refund.issued`, and
`refunds.transaction.status_changed`.

**Try it.** Log in as `dana`, open a transaction, and request a $700 refund (it goes to
pending approval). Log in as `erin`, approve it from `/refunds/approvals`, and check that
it is issued. Log in as `audrey` and check `/audit`.

### What the two tools show

- **Same controls, different rules.** KYC uses four-eyes for risky cases (watchlist hits).
  Refunds uses it above a money threshold. Both call the same `approvals.request` /
  `approvals.decide`, and neither has any custom auth, permission, or audit code.
- **No platform changes.** Neither tool needed a change to `core/`.
- **Self-contained.** Each tool lives in its own `apps/<tool>/` folder (permissions,
  models with the status rules, routes, templates, seed data, tests). It plugs into the
  platform by adding roles to `config/roles.py`, mounting its router in `main.py`, and
  adding its seed to `seed.py`.

## Adding another tool

Write `specs/<tool>.md` (see `specs/kyc.md` and `specs/refunds.md` for the format) and ask
Devin to build it. The procedure in `.agents/skills/new-internal-tool/SKILL.md` covers file
layout, naming (`<tool>:<resource>.<action>` permissions, `<tool>_` table prefixes,
`<tool>.<entity>.<verb>` audit actions), testing, and the required PR sections.

## Known gaps

- The KYC case page shows the SSN without auditing the read. The new-tool skill requires
  auditing views of sensitive personal data, but `apps/kyc` predates that rule.
- Denied requests (403) and rejected inputs (400) are not written to the audit log; only
  logins and successful changes are.

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
