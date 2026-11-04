"""Refunds settings."""

from decimal import Decimal

# Refunds above this amount (USD) need approval from a second person.
APPROVAL_THRESHOLD = Decimal("500.00")
