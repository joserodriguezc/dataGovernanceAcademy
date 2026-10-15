"""Grafo de linaje de columnas leído del warehouse (meta.lineage_edges)."""

from pathlib import Path

import networkx as nx

from academy.core.warehouse import connect


def load_graph(db: Path) -> nx.DiGraph:
    g = nx.DiGraph()
    with connect(db, read_only=True) as con:
        rows = con.execute("""
            SELECT source_table || '.' || source_column, target_table || '.' || target_column,
                   kind, expression
            FROM meta.lineage_edges
            WHERE source_column IS NOT NULL AND target_column IS NOT NULL""").fetchall()
    for source, target, kind, expression in rows:
        g.add_edge(source, target, kind=kind, expression=expression)
    return g
