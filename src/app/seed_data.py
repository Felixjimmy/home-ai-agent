"""Load optional idempotent development fixtures into the local database."""

from pathlib import Path

from app.database import database_connection, ensure_phase2_tables


def main() -> None:
    ensure_phase2_tables()
    seed_sql = Path(__file__).resolve().parent.parent / "db" / "seed.sql"
    with database_connection() as connection:
        connection.execute(seed_sql.read_text(encoding="utf-8"))
    print("Development fixtures are present; existing device and inventory rows were preserved.")


if __name__ == "__main__":
    main()
