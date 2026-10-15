"""Publicación del linaje en el warehouse: tablas meta.lineage_edges y meta.lineage_steps."""

import duckdb
import pandas as pd

from .lineage import Edge, TableStep


def write_lineage(con: duckdb.DuckDBPyConnection, edges: list[Edge],
                  steps: list[TableStep]) -> dict[str, int]:
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    frames = {
        "lineage_edges": pd.DataFrame([{
            "source_table": e.source_table, "source_column": e.source_column,
            "target_table": e.target_table, "target_column": e.target_column,
            "kind": e.kind, "expression": e.expression, "sql_file": e.sql_file,
        } for e in edges]),
        "lineage_steps": pd.DataFrame([{
            "target_table": s.target, "source_tables": ", ".join(s.sources),
            "filters": " AND ".join(s.filters) or None,
            "group_by": ", ".join(s.group_by) or None, "sql_file": s.sql_file,
        } for s in steps]),
    }
    for name, df in frames.items():
        con.register("_frame", df)
        con.execute(f"CREATE OR REPLACE TABLE meta.{name} AS SELECT * FROM _frame")
        con.unregister("_frame")
    return {name: len(df) for name, df in frames.items()}
