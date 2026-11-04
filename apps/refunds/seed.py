"""Fake refunds demo data. Customer and merchant names are invented."""

from datetime import date

from sqlalchemy.orm import Session

from apps.refunds.models import SETTLED, Transaction
from core.auth import create_user
from core.seed import DEMO_PASSWORD

# customer, amount (cents), date, merchant
TRANSACTIONS = [
    ("Juniper Ashcombe", 129900, date(2026, 10, 2), "Northwind Electronics"),
    ("Rafferty Gale", 4599, date(2026, 10, 4), "Bluefin Books"),
    ("Saoirse Penhallow", 89000, date(2026, 10, 7), "Copperline Travel"),
    ("Thaddeus Wren", 23450, date(2026, 10, 9), "Maple & Vine Grocers"),
    ("Odalys Fernhill", 64000, date(2026, 10, 12), "Summit Outdoor Co."),
    ("Bastian Coldwell", 1299, date(2026, 10, 15), "Pixelpine Games"),
    ("Marisol Thistle", 250000, date(2026, 10, 18), "Harborview Furniture"),
    ("Evander Quill", 7820, date(2026, 10, 21), "Lumen Coffee Roasters"),
    ("Clementine Haskett", 51000, date(2026, 10, 25), "Ironleaf Fitness"),
    ("Ptolemy Varga", 31575, date(2026, 10, 29), "Starling Pharmacy"),
]


def run(db: Session) -> None:
    create_user(db, "dana", DEMO_PASSWORD, ["support_agent"])
    create_user(db, "erin", DEMO_PASSWORD, ["support_lead"])
    for customer, cents, day, merchant in TRANSACTIONS:
        db.add(Transaction(customer_name=customer, amount_cents=cents, date=day,
                           merchant=merchant, status=SETTLED))
