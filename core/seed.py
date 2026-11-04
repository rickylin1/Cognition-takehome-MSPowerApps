from sqlalchemy.orm import Session

from core.auth import create_user

DEMO_PASSWORD = "demo-password"


def run(db: Session) -> None:
    create_user(db, "audrey", DEMO_PASSWORD, ["auditor"])
