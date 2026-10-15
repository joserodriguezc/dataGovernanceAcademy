"""Linaje a nivel de columna a partir del SQL de las transformaciones del warehouse.

Cada `CREATE TABLE ... AS SELECT` se analiza con sqlglot: se cualifican sus columnas con el
esquema real del warehouse y, para cada columna de la tabla destino, se anotan las columnas
de origen y la expresión que la calcula. Las tablas raw se enlazan con su sistema de origen
por el prefijo del nombre (crm_, ecom_, pos_, erp_).
"""

from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import networkx as nx
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

DIALECT = "duckdb"


@dataclass(frozen=True)
class Edge:
    source_table: str
    source_column: str | None  # None en las aristas de sistema → tabla raw
    target_table: str
    target_column: str | None
    kind: str  # carga | directo | renombrado | calculado | agregado | constante |
    #            filtro | clave de unión
    expression: str
    sql_file: str

    @property
    def source(self) -> str:
        return f"{self.source_table}.{self.source_column}" if self.source_column \
            else self.source_table

    @property
    def target(self) -> str:
        return f"{self.target_table}.{self.target_column}" if self.target_column \
            else self.target_table


@dataclass
class TableStep:
    """Una transformación: tabla destino, tablas de origen y filtros aplicados."""

    target: str
    sources: list[str]
    filters: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    sql_file: str = ""


def warehouse_schema(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, dict[str, str]]]:
    schema: dict[str, dict[str, dict[str, str]]] = {}
    for s, t, c, ty in con.execute(
            "SELECT table_schema, table_name, column_name, data_type FROM information_schema."
            "columns WHERE table_schema IN ('raw', 'staging', 'curated')").fetchall():
        schema.setdefault(s, {}).setdefault(t, {})[c] = ty
    return schema


def _selects(node: exp.Expression) -> list[exp.Select]:
    """Ramas SELECT de una consulta, aplanando UNION / UNION ALL."""
    if isinstance(node, exp.Select):
        return [node]
    if isinstance(node, exp.SetOperation):
        return _selects(node.left) + _selects(node.right)
    raise ValueError(f"consulta no soportada: {type(node).__name__}")


def _kind(projection: exp.Expression, target_column: str, sources: list[exp.Column]) -> str:
    inner = projection.this if isinstance(projection, exp.Alias) else projection
    if not sources:
        return "constante"
    if inner.find(exp.AggFunc):
        return "agregado"
    if isinstance(inner, exp.Column):
        return "directo" if inner.name == target_column else "renombrado"
    if isinstance(inner, exp.Cast) and isinstance(inner.this, exp.Column):
        return "conversión de tipo"
    return "calculado"


def cte_node(target: str, cte: str) -> str:
    """Nodo intermedio de una CTE: se nombra a partir de la tabla que la define."""
    return f"{target}__{cte}"


def _select_edges(select: exp.Select, target: str, step: TableStep, sql_file: str,
                  ctes: dict[str, str]) -> list[Edge]:
    edges = []
    tables = {t.alias_or_name: ctes.get(t.name) if not t.db and t.name in ctes
              else f"{t.db}.{t.name}" for t in select.find_all(exp.Table)}
    step.sources += [t for t in tables.values()
                     if t not in step.sources and t not in ctes.values()]
    where = select.args.get("where")
    if where:
        step.filters.append(where.this.sql(dialect=DIALECT))
    group = select.args.get("group")
    if group:
        step.group_by = [g.sql(dialect=DIALECT) for g in group.expressions]
    # Columnas de las claves de unión, por tabla unida
    join_keys: dict[str, list[exp.Column]] = {}
    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            join_keys[join.this.alias_or_name] = list(on.find_all(exp.Column))
    filter_cols = list(where.find_all(exp.Column)) if where else []
    for projection in select.expressions:
        column = projection.alias_or_name
        cols = list(projection.find_all(exp.Column))
        kind = _kind(projection, column, cols)
        inner = projection.this if isinstance(projection, exp.Alias) else projection
        expression = inner.sql(dialect=DIALECT)
        if not cols:  # constante: no hay columna de origen, pero sí transformación
            edges.append(Edge(target, None, target, column, kind, expression, sql_file))
        for c in cols:
            edges.append(Edge(tables[c.table], c.name, target, column, kind,
                              expression, sql_file))
        # Dependencias indirectas: el filtro decide qué filas llegan a la columna y
        # la clave de unión decide qué valor se trae de la tabla unida.
        indirect = [(c, "filtro", where.this) for c in filter_cols]
        for alias in {c.table for c in cols} & set(join_keys):
            indirect += [(c, "clave de unión", None) for c in join_keys[alias]]
        for c, how, node in indirect:
            text = node.sql(dialect=DIALECT) if node is not None else c.sql(DIALECT)
            edges.append(Edge(tables[c.table], c.name, target, column, how, text,
                              sql_file))
    return edges


def parse_sql(sql: str, sql_file: str, schema: dict) -> tuple[list[Edge], list[TableStep]]:
    """Aristas de columna de cada CREATE TABLE ... AS SELECT.

    Las CTE se recorren en orden como nodos intermedios (`cte_node`), así el linaje llega
    hasta las tablas de origen aunque la consulta use WITH.
    """
    edges, steps = [], []
    for stmt in sqlglot.parse(sql, dialect=DIALECT):
        if not isinstance(stmt, exp.Create) or stmt.expression is None:
            continue
        target = f"{stmt.this.db}.{stmt.this.name}"
        query = qualify(stmt.expression.copy(), schema=schema, dialect=DIALECT,
                        identify=False, quote_identifiers=False)
        step = TableStep(target, [], sql_file=sql_file)
        ctes: dict[str, str] = {}
        with_ = query.args.get("with_")
        if with_ is not None:
            query.set("with_", None)
            for cte in with_.expressions:
                node = cte_node(target, cte.alias)
                for select in _selects(cte.this):
                    edges += _select_edges(select, node, step, sql_file, ctes)
                ctes[cte.alias] = node
        for select in _selects(query):
            edges += _select_edges(select, target, step, sql_file, ctes)
        steps.append(step)
    return edges, steps


def source_edges(schema: dict, systems: dict[str, str]) -> list[Edge]:
    """Sistema de origen → tabla raw (carga del CSV sin transformar)."""
    edges = []
    for table in schema.get("raw", {}):
        prefix = table.split("_")[0]
        if prefix not in systems:
            continue
        edges.append(Edge(f"sistema.{prefix}", None, f"raw.{table}", None, "carga",
                          f"data/raw/{table}.csv", "dglab.warehouse.load_raw"))
    return edges


def build_lineage(con: duckdb.DuckDBPyConnection, sql_files: list[Path],
                  systems: dict[str, str]) -> tuple[list[Edge], list[TableStep]]:
    schema = warehouse_schema(con)
    edges, steps = source_edges(schema, systems), []
    for f in sql_files:
        e, s = parse_sql(f.read_text(encoding="utf-8"), f.name, schema)
        edges += e
        steps += s
    return edges + external_edges(con), steps


def external_edges(con: duckdb.DuckDBPyConnection) -> list[Edge]:
    """Linaje que registran procesos que no son SQL (p. ej. el PDM del capítulo 10)."""
    exists = con.execute("SELECT count(*) FROM information_schema.tables WHERE "
                         "table_schema = 'meta' AND table_name = 'lineage_external'"
                         ).fetchone()[0]
    if not exists:
        return []
    return [Edge(*row) for row in con.execute(
        "SELECT source_table, source_column, target_table, target_column, kind, expression, "
        "sql_file FROM meta.lineage_external").fetchall()]


def column_graph(edges: list[Edge]) -> nx.DiGraph:
    """Grafo de columnas: origen → destino (las constantes quedan como nodos sin origen)."""
    g = nx.DiGraph()
    for e in edges:
        if e.source_column and e.target_column:
            if not g.has_edge(e.source, e.target):  # la primera (directa) manda
                g.add_edge(e.source, e.target, kind=e.kind, expression=e.expression)
        elif e.target_column:
            g.add_node(e.target)
    return g


def table_graph(edges: list[Edge]) -> nx.DiGraph:
    g = nx.DiGraph()
    for e in edges:
        if e.source_table != e.target_table:
            g.add_edge(e.source_table, e.target_table)
    return g
