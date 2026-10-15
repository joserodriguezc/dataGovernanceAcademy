"""Publicación del PDM en el warehouse y modelo de consumo.

- `pdm.*`: el hub de datos primarios. Es el único lugar autorizado para los datos
  personales del cliente unificado (golden record, correspondencias y atribución).
- `curated.dim_customer`: lo que consume la analítica, sin datos personales directos.
- `pdm.customer_xref`: correspondencia registro de origen -> golden id. Es la base de la
  integración bidireccional: cada sistema puede recibir su golden id.
- El linaje de estas tablas se registra en `meta.lineage_external` (y en
  `meta.lineage_edges` si existe), porque no salen del SQL que analiza el capítulo 7.
"""

from datetime import date

import duckdb
import pandas as pd

LINEAGE_FILE = "academy.lessons.ch10"


def age_band(birth: object, today: date) -> str | None:
    if birth is None or pd.isna(birth):
        return None
    b = pd.Timestamp(birth).date()
    age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    for upper, label in ((25, "18-24"), (35, "25-34"), (45, "35-44"), (55, "45-54"),
                         (65, "55-64")):
        if age < upper:
            return label
    return "65+"


def _write(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    con.register("_frame", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _frame")
    con.unregister("_frame")


def publish(con: duckdb.DuckDBPyConnection, golden: pd.DataFrame, xref: pd.DataFrame,
            attribution: pd.DataFrame, reference: pd.DataFrame, review: pd.DataFrame,
            today: date) -> dict[str, int]:
    con.execute("CREATE SCHEMA IF NOT EXISTS pdm")
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    tables = {
        "pdm.customer_golden": golden,
        "pdm.customer_xref": xref,
        "pdm.customer_attribution": attribution,
        "pdm.customer_review_queue": review,
        "pdm.ref_province": reference,
    }
    for name, df in tables.items():
        _write(con, name, df)
    sales = con.execute("""
        WITH sales AS (
            SELECT x.golden_id, 'tienda' AS channel, s.amount
            FROM staging.stg_pos_sales s JOIN pdm.customer_xref x
              ON x.source = 'pos' AND x.source_id = s.card_id
            UNION ALL
            SELECT x.golden_id, 'online', o.amount
            FROM staging.stg_ecom_orders o JOIN pdm.customer_xref x
              ON x.source = 'ecom' AND x.source_id = o.ecom_user_id
            WHERE o.status NOT IN ('cancelado', 'devuelto'))
        SELECT golden_id, sum(amount) AS net_sales,
               count(DISTINCT channel) AS channels_purchased
        FROM sales GROUP BY golden_id""").df()
    dim = golden.merge(sales, on="golden_id", how="left")
    dim = pd.DataFrame({
        "golden_customer_id": dim["golden_id"],
        "province_code": dim["province_code"], "province": dim["province"],
        "community": dim["community"], "sales_region": dim["sales_region"],
        "age_band": dim["birth_date"].map(lambda b: age_band(b, today)),
        "loyalty_tier": dim["loyalty_tier"], "consent_marketing": dim["consent_marketing"],
        "in_crm": dim["in_crm"], "in_ecom": dim["in_ecom"], "in_pos": dim["in_pos"],
        "source_records": dim["source_records"],
        "net_sales": dim["net_sales"].fillna(0.0).round(2),
        "channels_purchased": dim["channels_purchased"].fillna(0).astype(int),
    })
    _write(con, "curated.dim_customer", dim)
    con.execute("COMMENT ON TABLE curated.dim_customer IS 'Cliente único (golden record) "
                "sin datos personales directos: localización, segmento, canales y ventas "
                "netas. Fuente autorizada: pdm.customer_golden.'")
    _write_lineage(con)
    return {name: len(df) for name, df in tables.items()} | {"curated.dim_customer": len(dim)}


def _write_lineage(con: duckdb.DuckDBPyConnection) -> None:
    edges = [
        (src, None, "pdm.customer_golden", None, "deduplicación y trust logic")
        for src in ("staging.stg_crm_customers", "staging.stg_ecom_customers",
                    "staging.stg_pos_loyalty_cards")
    ] + [
        ("pdm.customer_golden", "golden_id", "curated.dim_customer", "golden_customer_id",
         "renombrado"),
        ("pdm.customer_golden", "postal_code", "curated.dim_customer", "province",
         "enriquecido con datos de referencia"),
        ("pdm.customer_golden", "birth_date", "curated.dim_customer", "age_band",
         "calculado"),
        ("staging.stg_pos_sales", "amount", "curated.dim_customer", "net_sales", "agregado"),
        ("staging.stg_ecom_orders", "amount", "curated.dim_customer", "net_sales", "agregado"),
        ("staging.stg_ecom_orders", "status", "curated.dim_customer", "net_sales", "filtro"),
    ]
    df = pd.DataFrame(edges, columns=["source_table", "source_column", "target_table",
                                      "target_column", "kind"])
    df["expression"] = df["kind"]
    df["sql_file"] = LINEAGE_FILE
    _write(con, "meta.lineage_external", df)
    exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE "
                         "table_schema = 'meta' AND table_name = 'lineage_edges'").fetchone()[0]
    if exists:
        con.execute("DELETE FROM meta.lineage_edges WHERE sql_file = ?", [LINEAGE_FILE])
        con.execute("INSERT INTO meta.lineage_edges SELECT source_table, source_column, "
                    "target_table, target_column, kind, expression, sql_file "
                    "FROM meta.lineage_external")
