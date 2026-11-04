"""Fake KYC demo data. Names and addresses are invented; SSNs use the never-issued 9xx range."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from apps.kyc.models import PENDING, KycCase
from core.auth import create_user
from core.seed import DEMO_PASSWORD

# applicant, date of birth, address, ID document, document check, identity match, watchlist hit
CASES = [
    ("Mira Quellson", date(1988, 4, 12), "14 Larkspur Way, Springfield", "Passport", True, True, False),
    ("Tobin Vale", date(1975, 9, 30), "220 Harbor Rd, Fairview", "Driver's license", True, True, True),
    ("Odessa Brightwater", date(1992, 1, 5), "9 Cedar Ct, Riverton", "National ID", False, True, False),
    ("Linus Farrow", date(1983, 7, 21), "301 Elm St, Lakeside", "Passport", True, False, False),
    ("Priya Tallowmere", date(1990, 11, 2), "77 Orchard Ln, Hillcrest", "Driver's license", True, True, True),
    ("Caspian Roe", date(1969, 3, 17), "5 Birch Ave, Maplewood", "Passport", True, True, False),
    ("Wren Ashby", date(1998, 6, 8), "48 Quarry Rd, Stonebridge", "National ID", True, True, False),
    ("Dmitri Halloway", date(1979, 12, 25), "612 Pine St, Brookfield", "Passport", False, False, True),
    ("Ines Corvale", date(1986, 2, 14), "33 Willow Dr, Greenhaven", "Driver's license", True, True, False),
    ("Felix Marrowby", date(1994, 8, 19), "150 Summit Blvd, Eastport", "Passport", True, False, True),
]


def run(db: Session) -> None:
    create_user(db, "alice", DEMO_PASSWORD, ["kyc_analyst"])
    create_user(db, "carol", DEMO_PASSWORD, ["kyc_analyst"])
    create_user(db, "bob", DEMO_PASSWORD, ["kyc_senior_analyst"])
    create_user(db, "frank", DEMO_PASSWORD, ["kyc_analyst", "auditor"])

    now = datetime.now(timezone.utc)
    for i, (name, dob, address, doc, doc_ok, id_ok, watchlist) in enumerate(CASES, start=1):
        created = now - timedelta(hours=len(CASES) - i)
        db.add(KycCase(
            applicant_name=name, date_of_birth=dob, ssn=f"9{i:02d}-55-{1000 + i}",
            address=address, id_document_type=doc, document_check_passed=doc_ok,
            identity_match_passed=id_ok, watchlist_hit=watchlist, status=PENDING,
            created_at=created, updated_at=created,
        ))
