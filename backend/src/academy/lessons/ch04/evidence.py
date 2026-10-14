"""Evidencia objetiva del warehouse para contrastar las puntuaciones de los talleres.

La evaluación de madurez es subjetiva. Unos pocos indicadores medidos sobre los datos
reales acotan lo que la evidencia respalda: por ejemplo, si ninguna tabla está documentada,
la gestión de metadatos no puede estar por encima del nivel 2. Estos indicadores también
son la línea base de las métricas del plan de mejora (#9).
"""

from dataclasses import dataclass

import duckdb

# Controles de calidad: (nombre, consulta que devuelve la proporción de registros válidos)
DQ_CHECKS = {
    "Email informado en el CRM":
        "SELECT avg(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) FROM staging.stg_crm_customers",
    "Código postal válido en clientes online":
        "SELECT avg(CASE WHEN regexp_full_match(postal_code, '\\d{5}') THEN 1 ELSE 0 END) "
        "FROM staging.stg_ecom_customers",
    "Fecha de alta online en formato ISO":
        "SELECT avg(CASE WHEN regexp_full_match(created_at, '\\d{4}-\\d{2}-\\d{2}') "
        "THEN 1 ELSE 0 END) FROM raw.ecom_customers",
    "Precio unitario positivo en tienda":
        "SELECT avg(CASE WHEN unit_price > 0 THEN 1 ELSE 0 END) FROM staging.stg_pos_sales",
    "Producto con categoría":
        "SELECT avg(CASE WHEN category IS NOT NULL THEN 1 ELSE 0 END) FROM staging.stg_products",
}


@dataclass(frozen=True)
class Cap:
    """Nivel máximo que respalda la evidencia para una dimensión."""

    dimension: str
    indicator: str
    value: float
    max_level: int
    reason: str


def _scalar(con: duckdb.DuckDBPyConnection, sql: str) -> float:
    value = con.execute(sql).fetchone()[0]
    return float(value or 0.0)


def _table_exists(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> bool:
    return bool(con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [schema, table]).fetchone()[0])


def dq_checks(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    return {name: _scalar(con, sql) for name, sql in DQ_CHECKS.items()}


def indicators(con: duckdb.DuckDBPyConnection) -> dict[str, float]:
    """Indicadores objetivos (proporciones entre 0 y 1)."""
    checks = dq_checks(con)
    # Duplicados de cliente: en la fuente autorizada. Antes del capítulo 10 es el CRM;
    # después, el golden record del hub de datos primarios.
    customer_source = ("pdm.customer_golden" if _table_exists(con, "pdm", "customer_golden")
                       else "staging.stg_crm_customers")
    lineage = 0.0
    if _table_exists(con, "meta", "lineage_edges"):  # lo creará el capítulo 7
        lineage = _scalar(con, """
            SELECT count(DISTINCT e.target_table) / count(DISTINCT t.table_name)
            FROM duckdb_tables() t LEFT JOIN meta.lineage_edges e
              ON e.target_table = t.schema_name || '.' || t.table_name
            WHERE t.schema_name = 'curated'""")
    return {
        "documented_tables": _scalar(con, """
            SELECT avg(CASE WHEN comment IS NOT NULL AND comment <> '' THEN 1 ELSE 0 END)
            FROM duckdb_tables() WHERE schema_name = 'curated'"""),
        "lineage_coverage": lineage,
        "crm_duplicate_phones": _scalar(con, f"""
            SELECT avg(CASE WHEN n > 1 THEN 1 ELSE 0 END) FROM (
              SELECT count(*) OVER (PARTITION BY phone) AS n
              FROM {customer_source} WHERE phone IS NOT NULL)"""),
        "dq_pass_rate": sum(checks.values()) / len(checks),
        "dq_worst_check": min(checks.values()),
    }


def evidence_caps(ind: dict[str, float]) -> list[Cap]:
    """Reglas explícitas que acotan el nivel de cada dimensión según la evidencia."""
    caps = []
    if ind["documented_tables"] < 0.5:
        caps.append(Cap("metadata", "documented_tables", ind["documented_tables"], 2,
                        "Menos de la mitad de las tablas curated están documentadas."))
        caps.append(Cap("privacy_security", "documented_tables", ind["documented_tables"], 2,
                        "Sin documentación no hay clasificación de datos personales."))
    if ind["lineage_coverage"] < 0.5:
        caps.append(Cap("lineage", "lineage_coverage", ind["lineage_coverage"], 2,
                        "No hay linaje documentado para la mayoría de tablas curated."))
    if ind["crm_duplicate_phones"] > 0.01:
        caps.append(Cap("master_data", "crm_duplicate_phones", ind["crm_duplicate_phones"], 2,
                        "Más del 1 % de los clientes del CRM comparten teléfono con otro "
                        "registro: no hay registro único."))
    if ind["dq_worst_check"] < 0.98:
        caps.append(Cap("data_quality", "dq_worst_check", ind["dq_worst_check"], 3,
                        "Hay controles con más del 2 % de errores: los defectos no se "
                        "previenen en origen."))
    return caps
