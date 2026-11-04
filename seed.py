"""Reset the local database and load fake demo data: core seed first, then each tool's seed."""

from core.db import Base, SessionLocal, engine

SEEDS = []


def main() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for run in SEEDS:
            run(db)
        db.commit()
    print("Seeded database.")


if __name__ == "__main__":
    main()
