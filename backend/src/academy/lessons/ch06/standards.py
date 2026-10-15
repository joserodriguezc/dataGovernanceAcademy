"""Estándar de metadatos: cumplimiento por norma y por dominio, y métricas de madurez."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .catalog import CatalogColumn, CatalogTable
from .glossary import Glossary, Stewards, Term


class Publication(BaseModel):
    version: str
    owner: str
    accountable: str
    published: date
    next_review: date


class Standard(BaseModel):
    id: str
    applies_to: Literal["table", "column", "term"]
    check: str
    text: str


class StandardsInput(BaseModel):
    publication: Publication
    standards: list[Standard] = Field(min_length=1)


TABLE_CHECKS: dict[str, Callable[[CatalogTable], bool]] = {
    "has_description": lambda t: bool(t.annotation and t.annotation.description),
    "has_domain": lambda t: t.domain is not None,
    "has_business_steward": lambda t: bool(t.business_stewards),
    "has_technical_steward": lambda t: bool(t.technical_stewards),
}
COLUMN_CHECKS: dict[str, Callable[[CatalogColumn], bool]] = {
    "is_classified": lambda c: c.level is not None,
    "has_business_term": lambda c: c.term is not None,
}


def term_checks(stewards: dict[str, Stewards]) -> dict[str, Callable[[Term], bool]]:
    return {
        "has_definition": lambda t: bool(t.definition),
        "is_approved": lambda t: t.status == "approved",
        "has_steward": lambda t: bool(stewards.get(t.domain) and stewards[t.domain].business),
        "is_mapped": lambda t: bool(t.columns),
    }


@dataclass(frozen=True)
class Compliance:
    standard: Standard
    passed: int
    total: int
    by_domain: dict[str, tuple[int, int]]
    failures: list[str]

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 1.0


def evaluate(standards: list[Standard], tables: list[CatalogTable], glossary: Glossary,
             stewards: dict[str, Stewards]) -> list[Compliance]:
    """Cumplimiento de cada norma sobre las tablas de staging y curated y el glosario."""
    scoped = [t for t in tables if t.subject_to_standard]
    t_checks = term_checks(stewards)
    out = []
    for s in standards:
        if s.applies_to == "table":
            items = [(t.fqn, t.domain, TABLE_CHECKS[s.check](t)) for t in scoped]
        elif s.applies_to == "column":
            items = [(c.fqn, t.domain, COLUMN_CHECKS[s.check](c)) for t in scoped
                     for c in t.columns]
        else:
            items = [(term.term, term.domain, t_checks[s.check](term)) for term in glossary.terms]
        by_domain: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for _, domain, ok in items:
            by_domain[domain or "sin dominio"][0] += ok
            by_domain[domain or "sin dominio"][1] += 1
        out.append(Compliance(s, sum(ok for *_, ok in items), len(items),
                              {d: (p, n) for d, (p, n) in by_domain.items()},
                              [name for name, _, ok in items if not ok]))
    return out


def maturity_metrics(tables: list[CatalogTable], compliance: list[Compliance],
                     lineage_tables: set[str]) -> list[tuple[str, int, int]]:
    """Métricas de madurez del catálogo que propone el capítulo: (métrica, cumplen, total)."""
    scoped = [t for t in tables if t.subject_to_standard]
    table_ids = {c.standard.id for c in compliance if c.standard.applies_to == "table"}
    failing = {f for c in compliance if c.standard.id in table_ids for f in c.failures}
    return [
        ("Activos de datos en el catálogo", sum(t.annotation is not None for t in scoped),
         len(scoped)),
        ("Activos con información completa", sum(t.fqn not in failing for t in scoped),
         len(scoped)),
        ("Activos con stewards", sum(bool(t.business_stewards and t.technical_stewards)
                                     for t in scoped), len(scoped)),
        ("Activos certificados por su steward (capítulo 8)", 0, len(scoped)),
        ("Activos con linaje completo (capítulo 7)", sum(t.fqn in lineage_tables
                                                         for t in scoped), len(scoped)),
    ]
