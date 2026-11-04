"""Reset the local database and load fake demo data: core seed first, then each tool's seed."""

from apps.kyc import seed as kyc_seed
from apps.refunds import seed as refunds_seed
from core import approvals, audit  # noqa: F401  (register models)
from core import seed as core_seed
from core.db import Base, SessionLocal, engine

SEEDS = [core_seed.run, kyc_seed.run, refunds_seed.run]


def main() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for run in SEEDS:
            run(db)
        db.commit()
    print(f"Seeded database. Demo password for all users: {core_seed.DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
