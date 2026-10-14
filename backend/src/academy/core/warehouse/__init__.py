"""Warehouse DuckDB de NovaMercado en tres capas: raw, staging y curated.

- raw: los CSV tal como llegan de cada sistema, todo como texto.
- staging: tipos correctos y normalizaciones técnicas, sin corregir defectos de negocio.
- curated: modelo conformado (dimensiones, hechos de venta y cifra diaria por canal).

Las transformaciones son ficheros SQL numerados en `sql/`, que se ejecutan en orden.
"""

from pathlib import Path

import duckdb

from academy.core.paths import RAW_DIR, WAREHOUSE_DB

SQL_DIR = Path(__file__).parent / "sql"
LAYERS = ("raw", "staging", "curated")


def connect(db_path: Path = WAREHOUSE_DB, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), read_only=read_only)


def sql_files() -> list[Path]:
    """Transformaciones en orden de ejecución."""
    return sorted(SQL_DIR.glob("*.sql"))


def load_raw(con: duckdb.DuckDBPyConnection, raw_dir: Path = RAW_DIR) -> list[str]:
    """Carga cada CSV de `raw_dir` en el esquema raw, sin interpretar tipos."""
    csvs = sorted(raw_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No hay CSV en {raw_dir}: genera antes los datos en la "
                                "página «Datos de NovaMercado»")
    for layer in LAYERS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {layer}")
    for csv in csvs:
        path = csv.as_posix().replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE raw.{csv.stem} AS "
                    f"SELECT * FROM read_csv('{path}', header = true, all_varchar = true)")
    return [csv.stem for csv in csvs]


def run_transforms(con: duckdb.DuckDBPyConnection) -> list[str]:
    for sql in sql_files():
        con.execute(sql.read_text(encoding="utf-8"))
    return [sql.name for sql in sql_files()]


def table_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Filas de cada tabla del warehouse, como 'esquema.tabla'."""
    tables = con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema IN ('raw', 'staging', 'curated') ORDER BY 1, 2").fetchall()
    return {f"{s}.{t}": con.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
            for s, t in tables}


def build_warehouse(db_path: Path = WAREHOUSE_DB, raw_dir: Path = RAW_DIR) -> dict[str, int]:
    """Carga raw, ejecuta las transformaciones y devuelve las filas por tabla."""
    with connect(db_path) as con:
        load_raw(con, raw_dir)
        run_transforms(con)
        return table_counts(con)
