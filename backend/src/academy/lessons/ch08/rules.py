"""Reglas de calidad: definición, ejecución con pandera y resultados por regla.

Cada regla se traduce en un esquema de pandera de una sola columna y una sola comprobación,
y se valida en modo `lazy` sobre la tabla indexada por su clave: así se obtienen los
registros concretos que fallan, no solo un porcentaje.
"""

import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import duckdb
import pandas as pd
import pandera.pandas as pa
from pydantic import BaseModel, Field, model_validator

from academy.core.company import DATA_DOMAINS

warnings.filterwarnings("ignore", module="pandera")

RuleType = Literal["not_null", "regex", "positive", "in_set", "unique", "references",
                   "condition", "freshness"]
DIMENSIONS = ("completitud", "validez", "consistencia", "exactitud", "unicidad", "integridad",
              "actualidad")
OK = "__ok"


class TableSpec(BaseModel):
    key: str
    domain: str

    @model_validator(mode="after")
    def _domain(self) -> "TableSpec":
        if self.domain not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{self.domain}'")
        return self


class Rule(BaseModel):
    id: str
    table: str
    column: str
    type: RuleType
    dimension: Literal["completitud", "validez", "consistencia", "exactitud", "unicidad",
                       "integridad", "actualidad"]
    severity: int = Field(ge=1, le=3)
    threshold: float = Field(gt=0, le=1)
    remediation: Literal["estandarizar", "excluir", "corregir_en_origen", "enriquecer",
                         "aceptar"]
    description: str
    pattern: str | None = None
    values: list[str] | None = None
    ref: str | None = None
    condition: str | None = None
    max_age_days: int | None = None

    @model_validator(mode="after")
    def _params(self) -> "Rule":
        needed = {"regex": "pattern", "in_set": "values", "references": "ref",
                  "condition": "condition", "freshness": "max_age_days"}.get(self.type)
        if needed and getattr(self, needed) is None:
            raise ValueError(f"{self.id}: la regla {self.type} necesita '{needed}'")
        return self


class Disposition(BaseModel):
    decision: str
    by: str
    date: date
    reason: str


class Certification(BaseModel):
    max_severity_blocking: int = Field(1, ge=1, le=3)


class Value(BaseModel):
    contacts_marketing_value: float = Field(ge=0)
    hours_manual_fix_per_issue: float = Field(ge=0)
    cost_per_hour: float = Field(ge=0)


class DQInput(BaseModel):
    as_of: date
    tables: dict[str, TableSpec]
    rules: list[Rule] = Field(min_length=1)
    seeded_defects: dict[str, str] = Field(default_factory=dict)
    dispositions: dict[str, Disposition] = Field(default_factory=dict)
    certification: Certification = Certification()
    value: Value

    @model_validator(mode="after")
    def _refs(self) -> "DQInput":
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de regla repetidos")
        unknown = [r.id for r in self.rules if r.table not in self.tables]
        if unknown:
            raise ValueError(f"reglas sobre tablas sin clave declarada: {unknown}")
        bad = (set(self.seeded_defects.values()) | set(self.dispositions)) - set(ids)
        if bad:
            raise ValueError(f"referencias a reglas inexistentes: {sorted(bad)}")
        return self


@dataclass
class RuleResult:
    rule: Rule
    total: int
    failed_keys: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def failed(self) -> int:
        return len(self.failed_keys)

    @property
    def pass_rate(self) -> float:
        return 1 - self.failed / self.total if self.total else 1.0

    @property
    def meets_threshold(self) -> bool:
        return self.pass_rate >= self.rule.threshold


def _check(rule: Rule, con: duckdb.DuckDBPyConnection) -> pa.Column:
    if rule.type == "not_null":
        return pa.Column(None, nullable=False)
    if rule.type == "unique":
        return pa.Column(None, nullable=True, unique=True)
    if rule.type == "regex":
        return pa.Column(None, pa.Check.str_matches(rule.pattern), nullable=True)
    if rule.type == "positive":
        return pa.Column(None, pa.Check.gt(0), nullable=True)
    if rule.type == "in_set":
        return pa.Column(None, pa.Check.isin(rule.values), nullable=True)
    if rule.type == "references":
        table, column = rule.ref.rsplit(".", 1)
        keys = [r[0] for r in con.execute(f'SELECT DISTINCT "{column}" FROM {table}').fetchall()]
        return pa.Column(None, pa.Check.isin(keys), nullable=True)
    raise ValueError(rule.type)


def run_rule(con: duckdb.DuckDBPyConnection, rule: Rule, key: str,
             as_of: date) -> RuleResult:
    if rule.type == "freshness":  # regla sobre el conjunto de datos, no sobre registros
        latest = con.execute(f'SELECT max("{rule.column}") FROM {rule.table}').fetchone()[0]
        age = (as_of - latest).days if latest else None
        ok = age is not None and age <= rule.max_age_days
        note = f"Último dato: {latest:%d/%m/%Y} ({age} días)" if latest else "Tabla vacía"
        return RuleResult(rule, 1, [] if ok else [rule.table], note)
    if rule.type == "condition":
        df = con.execute(f'SELECT CAST("{key}" AS VARCHAR) AS k, ({rule.condition}) AS {OK} '
                         f"FROM {rule.table}").df().set_index("k")
        column, check = OK, pa.Column(None, pa.Check.isin([True]), nullable=False)
    else:
        df = con.execute(f'SELECT CAST("{key}" AS VARCHAR) AS k, "{rule.column}" '
                         f"FROM {rule.table}").df().set_index("k")
        column, check = rule.column, _check(rule, con)
    try:
        pa.DataFrameSchema({column: check}).validate(df, lazy=True)
        failed: list[str] = []
    except pa.errors.SchemaErrors as err:
        failed = sorted(set(err.failure_cases["index"].dropna().astype(str)))
    return RuleResult(rule, len(df), failed)


def run_rules(con: duckdb.DuckDBPyConnection, inp: DQInput) -> list[RuleResult]:
    return [run_rule(con, r, inp.tables[r.table].key, inp.as_of) for r in inp.rules]


def scorecard(results: list[RuleResult], group: Callable[[RuleResult], str]) -> pd.DataFrame:
    """Por grupo: reglas, reglas que cumplen su umbral y tasa media de registros válidos."""
    df = pd.DataFrame([{"group": group(r), "meets": r.meets_threshold, "pass_rate": r.pass_rate}
                       for r in results])
    return df.groupby("group").agg(rules=("meets", "size"), meets=("meets", "sum"),
                                   pass_rate=("pass_rate", "mean"))
