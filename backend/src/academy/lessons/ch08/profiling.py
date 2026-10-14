"""Perfilado de datos: nulos, cardinalidad, rangos y patrones de formato por columna.

El patrón describe la forma del valor, no su longitud: cada secuencia de dígitos se
convierte en 9 y cada secuencia de letras y espacios en A ("2025-03-12" -> "9-9-9",
"12/03/2025" -> "9/9/9", "28A13" -> "9A9", "Ana María" -> "A"). Si una columna tiene
varios patrones frecuentes, hay un problema de consistencia.
"""

from dataclasses import dataclass

import duckdb

PATTERN_SQL = ("regexp_replace(regexp_replace(CAST(\"{c}\" AS VARCHAR), '[0-9]+', '9', 'g'), "
               "'[A-Za-zÀ-ÿ ]+', 'A', 'g')")


@dataclass(frozen=True)
class ColumnProfile:
    table: str
    column: str
    data_type: str
    rows: int
    null_rate: float
    distinct: int
    min_value: str | None
    max_value: str | None
    top_patterns: list[tuple[str, float]]  # (patrón, % de valores no nulos)

    @property
    def mixed_formats(self) -> bool:
        """Más de un patrón con al menos el 5 % de los valores."""
        return sum(share >= 0.05 for _, share in self.top_patterns) > 1


def profile_table(con: duckdb.DuckDBPyConnection, table: str, top: int = 3) -> list[ColumnProfile]:
    schema, name = table.split(".")
    cols = con.execute("SELECT column_name, data_type FROM information_schema.columns "
                       "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                       [schema, name]).fetchall()
    rows = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    out = []
    for c, dtype in cols:
        nulls, distinct, lo, hi = con.execute(
            f'SELECT count(*) - count("{c}"), count(DISTINCT "{c}"), '
            f'CAST(min("{c}") AS VARCHAR), CAST(max("{c}") AS VARCHAR) FROM {table}').fetchone()
        non_null = rows - nulls
        patterns = con.execute(
            f"SELECT {PATTERN_SQL.format(c=c)} AS p, count(*) FROM {table} "
            f'WHERE "{c}" IS NOT NULL GROUP BY p ORDER BY 2 DESC, p LIMIT {top}').fetchall()
        out.append(ColumnProfile(
            table, c, dtype, rows, nulls / rows if rows else 0.0, distinct, lo, hi,
            [(p, n / non_null) for p, n in patterns] if non_null else []))
    return out
