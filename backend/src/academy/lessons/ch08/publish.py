"""Publicación en el warehouse: resultados, incidencias y marca de certificado en el catálogo."""

import duckdb
import pandas as pd

from .quality import CertificationResult, Issue
from .rules import RuleResult


def write_quality(con: duckdb.DuckDBPyConnection, results: list[RuleResult], issues: list[Issue],
                  certs: list[CertificationResult], as_of) -> dict[str, int]:
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    frames = {
        "dq_results": pd.DataFrame([{
            "rule_id": r.rule.id, "table_fqn": r.rule.table, "column_name": r.rule.column,
            "dimension": r.rule.dimension, "severity": r.rule.severity,
            "threshold": r.rule.threshold, "records": r.total, "failed": r.failed,
            "pass_rate": r.pass_rate, "meets_threshold": r.meets_threshold, "measured_on": as_of,
        } for r in results]),
        "dq_issues": pd.DataFrame([{
            "issue_id": i.id, "rule_id": i.result.rule.id, "severity": i.severity,
            "steward": i.steward, "status": i.status, "failed_records": i.result.failed,
            "disposition": i.disposition,
        } for i in issues], columns=["issue_id", "rule_id", "severity", "steward", "status",
                                     "failed_records", "disposition"]),
    }
    for name, df in frames.items():
        con.register("_frame", df)
        con.execute(f"CREATE OR REPLACE TABLE meta.{name} AS SELECT * FROM _frame")
        con.unregister("_frame")
    has_catalog = con.execute("SELECT count(*) FROM information_schema.tables WHERE "
                              "table_schema = 'meta' AND table_name = 'catalog_tables'"
                              ).fetchone()[0]
    if has_catalog:  # la marca de certificado se ve en el marketplace del capítulo 6
        con.execute("UPDATE meta.catalog_tables SET certified = false")
        for c in certs:
            if c.certified:
                con.execute("UPDATE meta.catalog_tables SET certified = true WHERE table_fqn = ?",
                            [c.table])
    return {name: len(df) for name, df in frames.items()}
