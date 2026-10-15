"""Linter de arquitectura: comprueba los estándares sobre el SQL y sobre el warehouse.

- `lint_sql`: revisa una transformación antes de incorporarla (uso en el SDLC).
- `lint_warehouse`: revisa el esquema que ya existe (nomenclatura, tipos, claves,
  documentación y localización de los datos personales).

Los datos personales se detectan por el nombre de la columna con la política de
clasificación del capítulo 6, sin necesidad de leer los datos.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import duckdb
import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

from academy.lessons.ch06.classify import ClassificationPolicy, classify
from academy.lessons.ch07.lineage import DIALECT, _selects, warehouse_schema


class Naming(BaseModel):
    staging_prefixes: list[str]
    curated_prefixes: list[str]
    column_pattern: str


class Types(BaseModel):
    date_suffixes: list[str]
    date_types: list[str]
    money_names: list[str]
    money_types: list[str]


class Standard(BaseModel):
    id: str
    area: str
    text: str


class StandardsInput(BaseModel):
    naming: Naming
    allowed_reads: dict[str, list[str]]
    types: Types
    keys: dict[str, str]
    max_pii_locations: int = Field(ge=1)
    standards: list[Standard] = Field(min_length=1)


@dataclass(frozen=True)
class Finding:
    standard: str
    target: str
    message: str


class Linter:
    def __init__(self, std: StandardsInput, policy: ClassificationPolicy) -> None:
        self.std = std
        self.policy = policy
        self.pii_places: dict[str, set[str]] = {}  # categoría -> tablas (tras lint_warehouse)

    # --- utilidades --------------------------------------------------------------------
    def table_name_ok(self, fqn: str) -> bool:
        schema, name = fqn.split(".")
        prefixes = {"staging": self.std.naming.staging_prefixes,
                    "curated": self.std.naming.curated_prefixes}.get(schema)
        return prefixes is None or name.startswith(tuple(prefixes))

    def column_name_ok(self, column: str) -> bool:
        return bool(re.fullmatch(self.std.naming.column_pattern, column))

    def pii_category(self, column: str, fqn: str | None = None) -> str | None:
        """Categoría de PII restringida según el nombre de la columna (y las correcciones de
        los stewards del capítulo 6 si se da la columna completa), o None."""
        c = classify(fqn or f"x.x.{column}", column, [], self.policy)
        return c.category if self.policy.is_restricted(c.level) else None

    # --- SQL (SDLC) --------------------------------------------------------------------
    def lint_sql(self, sql: str, schema: dict) -> list[Finding]:
        findings = []
        for stmt in sqlglot.parse(sql, dialect=DIALECT):
            if not isinstance(stmt, exp.Create) or stmt.expression is None:
                continue
            target = f"{stmt.this.db}.{stmt.this.name}"
            layer = stmt.this.db
            if not self.table_name_ok(target):
                findings.append(Finding("ARQ-01", target, "El nombre no sigue la nomenclatura "
                                        f"de la capa {layer}."))
            if any(isinstance(p, exp.Star) or (isinstance(p, exp.Column)
                                               and isinstance(p.this, exp.Star))
                   for s in _selects(stmt.expression) for p in s.expressions):
                findings.append(Finding("ARQ-04", target, "Usa SELECT *: las columnas nuevas "
                                        "de la fuente llegarían sin control."))
            sources = sorted({f"{t.db}.{t.name}" for t in stmt.expression.find_all(exp.Table)})
            allowed = self.std.allowed_reads.get(layer)
            for s in sources:
                if allowed is not None and s.split(".")[0] not in allowed:
                    findings.append(Finding("ARQ-03", target, f"Lee de {s}: la capa {layer} "
                                            f"solo puede leer de {', '.join(allowed)}."))
            query = qualify(stmt.expression.copy(), schema=schema, dialect=DIALECT,
                            identify=False, quote_identifiers=False)
            columns = [p.alias_or_name for s in _selects(query) for p in s.expressions]
            # La nomenclatura se revisa en el SQL original: qualify normaliza a minúsculas
            written = [p.alias_or_name for s in _selects(stmt.expression) for p in s.expressions
                       if not p.find(exp.Star)]
            for c in written:
                if not self.column_name_ok(c):
                    findings.append(Finding("ARQ-02", target, f"La columna «{c}» no está en "
                                            "snake_case."))
            if layer == "curated":
                pii = sorted({c for c in columns if self.pii_category(c)})
                if pii:
                    findings.append(Finding("ARQ-09", target, "Lleva datos personales "
                                            f"restringidos a curated: {', '.join(pii)}."))
        return findings

    # --- Warehouse ---------------------------------------------------------------------
    def lint_warehouse(self, con: duckdb.DuckDBPyConnection) -> list[Finding]:
        findings = []
        cols = con.execute("""
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema IN ('raw', 'staging', 'curated')
            ORDER BY 1, 2, ordinal_position""").fetchall()
        tables = sorted({f"{s}.{t}" for s, t, _, _ in cols})
        documented = {f"{s}.{t}" for s, t in con.execute(
            "SELECT schema_name, table_name FROM duckdb_tables() WHERE comment <> ''"
        ).fetchall()}
        t = self.std.types
        pii_places: dict[str, set[str]] = defaultdict(set)
        for table in tables:
            if not self.table_name_ok(table):
                findings.append(Finding("ARQ-01", table, "El nombre no sigue la nomenclatura "
                                        "de su capa."))
            if table.startswith("curated.") and table not in documented:
                findings.append(Finding("ARQ-08", table, "Tabla curada sin documentar."))
        for schema, table, column, dtype in cols:
            fqn = f"{schema}.{table}"
            if not self.column_name_ok(column):
                findings.append(Finding("ARQ-02", f"{fqn}.{column}", "No está en snake_case."))
            if schema == "raw":
                continue  # raw guarda los datos tal como llegan: solo se revisa el nombre
            base = dtype.split("(")[0]
            if column.endswith(tuple(t.date_suffixes)) and base not in t.date_types:
                findings.append(Finding("ARQ-05", f"{fqn}.{column}",
                                        f"Fecha guardada como {dtype}."))
            if column in t.money_names and base not in t.money_types:
                findings.append(Finding("ARQ-06", f"{fqn}.{column}",
                                        f"Importe guardado como {dtype}."))
            category = self.pii_category(column, f"{fqn}.{column}")
            if category:
                pii_places[category].add(fqn)
                if schema == "curated":
                    findings.append(Finding("ARQ-09", f"{fqn}.{column}",
                                            f"Dato personal restringido ({category}) en curated."))
        for table, key in self.std.keys.items():
            if table not in tables:
                findings.append(Finding("ARQ-07", table, "La tabla declarada no existe."))
                continue
            n, distinct, nulls = con.execute(
                f'SELECT count(*), count(DISTINCT "{key}"), count(*) - count("{key}") '
                f"FROM {table}").fetchone()
            if distinct != n or nulls:
                findings.append(Finding("ARQ-07", table, f"La clave {key} no es única y no "
                                        f"nula ({n - distinct} repetidos, {nulls} nulos)."))
        self.pii_places = dict(pii_places)
        for category, places in sorted(pii_places.items()):
            if len(places) > self.std.max_pii_locations:
                findings.append(Finding("ARQ-10", category, f"Se guarda en {len(places)} "
                                        f"tablas: {', '.join(sorted(places))}."))
        return findings


def lint_files(linter: Linter, con: duckdb.DuckDBPyConnection, files) -> dict[str, list]:
    schema = warehouse_schema(con)
    return {str(f): linter.lint_sql(f.read_text(encoding="utf-8"), schema) for f in files}
