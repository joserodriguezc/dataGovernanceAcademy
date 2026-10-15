"""Publicación de los metadatos en el warehouse.

- COMMENT ON TABLE / COLUMN con la descripción de negocio (la ven todas las herramientas).
- Esquema `meta` con el glosario y el catálogo, que es la base del marketplace de datos.
"""

import duckdb
import pandas as pd

from .catalog import CatalogTable
from .glossary import Glossary, Stewards


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def write_comments(con: duckdb.DuckDBPyConnection, tables: list[CatalogTable],
                   glossary: Glossary) -> int:
    """Escribe las descripciones de tablas y columnas; devuelve cuántos comentarios escribió."""
    definitions = {t.term: t.definition for t in glossary.terms}
    written = 0
    for t in tables:
        if t.annotation:
            con.execute(f"COMMENT ON TABLE {t.fqn} IS {_quote(t.annotation.description)}")
            written += 1
        for c in t.columns:
            if c.term:
                text = f"{c.term}: {definitions[c.term]}"
                con.execute(f'COMMENT ON COLUMN {t.fqn}."{c.name}" IS {_quote(text)}')
                written += 1
    return written


def write_meta(con: duckdb.DuckDBPyConnection, tables: list[CatalogTable], glossary: Glossary,
               stewards: dict[str, Stewards], level_names: dict[str, str]) -> dict[str, int]:
    """Crea (o reemplaza) las tablas del esquema meta."""
    con.execute("CREATE SCHEMA IF NOT EXISTS meta")
    empty = Stewards([], [])
    frames = {
        "glossary": pd.DataFrame([{
            "term": t.term, "domain": t.domain, "definition": t.definition,
            "synonyms": ", ".join(t.synonyms), "antonyms": ", ".join(t.antonyms),
            "status": t.status, "authorized_source": t.authorized_source,
            "business_steward": ", ".join(stewards.get(t.domain, empty).business),
            "technical_steward": ", ".join(stewards.get(t.domain, empty).technical),
        } for t in glossary.terms]),
        "term_columns": pd.DataFrame(
            [{"term": t.term, "column_fqn": c} for t in glossary.terms for c in t.columns],
            columns=["term", "column_fqn"]),
        "catalog_tables": pd.DataFrame([{
            "table_fqn": t.fqn, "layer": t.layer, "domain": t.domain,
            "description": t.annotation.description if t.annotation else None,
            "format": t.annotation.format if t.annotation else None,
            "tags": ", ".join(t.annotation.tags) if t.annotation else None,
            "business_steward": ", ".join(t.business_stewards),
            "technical_steward": ", ".join(t.technical_stewards),
            "row_count": t.rows, "certified": False,
        } for t in tables]),
        "catalog_columns": pd.DataFrame([{
            "table_fqn": t.fqn, "column_name": c.name, "data_type": c.data_type,
            "null_rate": c.null_rate, "business_term": c.term, "classification": c.level,
            "classification_label": level_names.get(c.level or "", None),
            "category": c.category, "detection_method": c.method,
        } for t in tables for c in t.columns]),
    }
    for name, df in frames.items():
        con.register("_frame", df)
        con.execute(f"CREATE OR REPLACE TABLE meta.{name} AS SELECT * FROM _frame")
        con.unregister("_frame")
    return {name: len(df) for name, df in frames.items()}
