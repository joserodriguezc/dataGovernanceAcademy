"""Marketplace de datos: búsqueda en el glosario y el catálogo publicados en el warehouse.

Uso:
    uv run python -m academy.lessons.ch06.marketplace "cliente"
    uv run python -m academy.lessons.ch06.marketplace "ventas" --solo-certificados
"""


import duckdb


def search(con: duckdb.DuckDBPyConnection, text: str,
           certified_only: bool = False) -> dict[str, list[tuple]]:
    """Busca en términos, sinónimos, definiciones, tablas, etiquetas y columnas."""
    like = f"%{text.lower()}%"
    terms = con.execute("""
        SELECT term, status, definition, business_steward, authorized_source
        FROM meta.glossary
        WHERE lower(term) LIKE ? OR lower(synonyms) LIKE ? OR lower(definition) LIKE ?
        ORDER BY (lower(term) LIKE ?) DESC, term""", [like, like, like, like]).fetchall()
    tables = con.execute(f"""
        SELECT table_fqn, domain, description, business_steward, certified
        FROM meta.catalog_tables
        WHERE layer <> 'raw' {"AND certified" if certified_only else ""}
          AND (lower(table_fqn) LIKE ? OR lower(description) LIKE ? OR lower(tags) LIKE ?)
        ORDER BY table_fqn""", [like, like, like]).fetchall()
    columns = con.execute("""
        SELECT table_fqn || '.' || column_name, business_term, classification_label
        FROM meta.catalog_columns
        WHERE table_fqn NOT LIKE 'raw.%'
          AND (lower(column_name) LIKE ? OR lower(business_term) LIKE ?)
        ORDER BY 1""", [like, like]).fetchall()
    return {"terms": terms, "tables": tables, "columns": columns}
