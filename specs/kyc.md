# KYC Review Queue (`apps/kyc`)

Reviewer-facing tool for working KYC cases. This is the human review layer only: intake,
vendor checks, and automated decisioning happen elsewhere and are represented by seed data.

Use ONLY `core/` for auth, permissions, audit, and approvals. If a generic mechanism is
missing (something any app could use, written without KYC-specific names or rules), add it
to `core/` with tests. KYC business rules always stay in `apps/kyc/`. Do not move logic
into `core/` just because it might be reusable later.
List every change to `core/` separately in the PR description so it can be reviewed on its own.

## Data

Seed 10 fake cases. Each case has: applicant name, date of birth, SSN (fake), address,
ID document type, mock check results (document check pass/fail, identity match pass/fail,
watchlist hit yes/no), status, and timestamps. At least 3 cases have a watchlist hit.

## Permissions (`apps/kyc/permissions.py`)

- `kyc:case.view`
- `kyc:case.decide` (approve / reject)
- `kyc:case.second_review` (decide cases that need four-eyes review)

## Roles (`config/roles.py`)

- `kyc_analyst`: `kyc:case.view`, `kyc:case.decide`
- `kyc_senior_analyst`: `kyc:case.view`, `kyc:case.decide`, `kyc:case.second_review`

## Seed users

- `alice` (kyc_analyst), `carol` (kyc_analyst), `bob` (kyc_senior_analyst)
- `frank` (kyc_analyst + auditor): a compliance analyst who can also view the audit log

## Screens

- Queue (`/kyc`): list of cases showing applicant name, check summary, status.
- Case detail (`/kyc/cases/{id}`): applicant data, check results, and decision buttons
  (approve / reject) with a required reason.
- Senior analysts see an "Awaiting second review" section on the queue page.

## Statuses

- `PENDING → APPROVED | REJECTED`
- If the case has a watchlist hit: the analyst's decision creates an approval request via
  `core/approvals`, and the case moves to `PENDING_SECOND_REVIEW` with the proposed decision.
- `PENDING_SECOND_REVIEW → APPROVED | REJECTED` when a different user with
  `kyc:case.second_review` decides.
- Any other transition raises an error.

## Rules

- Every decision requires a reason and is written to the audit log with before/after status.
- The user who submitted a watchlist case cannot give its second review.

## Tests (required, in `apps/kyc/tests/`)

Use the shared fixtures from the root `conftest.py`. Test KYC rules only; do not re-test core.


- An analyst without `kyc:case.second_review` cannot decide a case in `PENDING_SECOND_REVIEW`.
- The same user cannot submit and second-review a case.
- A non-watchlist case is approved directly by an analyst.
- Every decision creates an audit entry.
- An illegal status transition raises an error.

## Out of scope

Escalation, case assignment, filters, PII masking, intake, vendor integrations,
rules engine, customer information requests, notifications, reporting.

## Done when

`pytest` passes (both `pytest core` and `pytest apps/kyc`). Start the app, log in as `alice`, submit a decision on a watchlist case,
log in as `bob`, give the second review, and confirm the entries on `/audit` (as `audrey`).
Attach screenshots of each step to the PR.
