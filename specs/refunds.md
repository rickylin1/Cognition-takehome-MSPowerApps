# Refunds Dashboard (`apps/refunds`)

Tool for support staff to issue refunds on customer transactions. Payment processing is
mocked: "issuing" a refund only records it. Follow the conventions in the
`new-internal-tool` skill.

## Data

Seed 10 fake transactions: customer name, amount, date, merchant, status.

## Permissions

- `refunds:transaction.view`
- `refunds:refund.request`
- `refunds:refund.approve`

## Roles

- `support_agent`: view, request
- `support_lead`: view, request, approve

## Seed users

- `dana` (support_agent), `erin` (support_lead)

## Screens

- Transactions list (`/refunds`), transaction detail with a refund form (amount + reason),
  and a "Pending approvals" list for users with `refunds:refund.approve`.

## Rules

- A refund cannot exceed the transaction amount minus refunds already issued.
- Refunds up to the approval threshold are issued immediately.
- Refunds above the threshold need approval from a different user with `refunds:refund.approve`.
- The threshold is $500, set in `config/refunds.py`.
- Every refund request, approval, rejection, and issuance is audited.

## Done when

`pytest` passes, with refunds tests in `apps/refunds/tests/`. Log in as `dana`, request a $700 refund, log in as `erin`, approve it,
and confirm the audit entries. Attach screenshots to the PR.
