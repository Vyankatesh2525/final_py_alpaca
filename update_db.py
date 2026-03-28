# update_db.py - Auto-diffing schema migration for Clau Trading Backend.
# Compares SQLAlchemy models against the live DB and applies whatever is missing.
# Safe to run multiple times — skips anything that already exists.
from sqlalchemy import inspect, text
from database import Base, engine

# Import all model modules so their classes are registered on Base.metadata
import models       # Wallet, Position, Trade, Payment, AlpacaToken
import auth_models  # User


def get_live_schema(conn) -> dict[str, set[str]]:
    """Return {table_name: {col_name, ...}} for every table currently in the DB."""
    inspector = inspect(conn)
    return {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }


def pg_type(col) -> str:
    """Best-effort mapping from SQLAlchemy column type to a Postgres DDL type."""
    t = str(col.type).upper()
    mapping = {
        "INTEGER":   "INTEGER",
        "FLOAT":     "DOUBLE PRECISION",
        "BOOLEAN":   "BOOLEAN",
        "VARCHAR":   "VARCHAR",
        "TEXT":      "TEXT",
        "DATETIME":  "TIMESTAMPTZ",
        "TIMESTAMP": "TIMESTAMPTZ",
    }
    for key, pg in mapping.items():
        if t.startswith(key):
            return pg
    return "VARCHAR"  # safe fallback for anything exotic


def run():
    ok = skipped = failed = 0

    with engine.connect() as conn:
        live = get_live_schema(conn)

        for table_name, table in Base.metadata.tables.items():

            # ── Table doesn't exist yet → CREATE ─────────────────────────────
            if table_name not in live:
                try:
                    table.create(bind=engine)
                    conn.commit()
                    print(f"  ✅  CREATE TABLE {table_name}")
                    ok += 1
                except Exception as e:
                    conn.rollback()
                    print(f"  ❌  CREATE TABLE {table_name}: {e}")
                    failed += 1
                continue

            # ── Table exists → check for missing columns ──────────────────────
            live_cols = live[table_name]
            for col in table.columns:
                if col.name in live_cols:
                    continue  # already there

                nullable    = "NOT NULL" if not col.nullable else ""
                default_sql = ""
                if col.default is not None and col.default.is_scalar:
                    default_sql = f"DEFAULT {col.default.arg!r}"
                elif col.server_default is not None:
                    default_sql = f"DEFAULT {col.server_default.arg}"

                ddl = (
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {col.name} {pg_type(col)} "
                    f"{default_sql} {nullable}".strip()
                )

                try:
                    conn.execute(text(ddl))
                    conn.commit()
                    print(f"  ✅  {table_name}.{col.name}  ({pg_type(col)})")
                    ok += 1
                except Exception as e:
                    conn.rollback()
                    err = str(e).lower()
                    if "already exists" in err or "duplicate" in err:
                        print(f"  ⏭️   {table_name}.{col.name} (already exists)")
                        skipped += 1
                    else:
                        print(f"  ❌  {table_name}.{col.name}: {e}")
                        failed += 1

    print(f"\n{ok} applied · {skipped} skipped · {failed} failed")


if __name__ == "__main__":
    run()