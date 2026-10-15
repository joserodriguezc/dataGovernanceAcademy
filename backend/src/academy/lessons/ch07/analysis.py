"""Uso del linaje: impacto, origen de una cifra, validación, hallazgos, madurez y valor."""

from dataclasses import dataclass

import networkx as nx
from pydantic import BaseModel, Field

from .lineage import Edge, TableStep


class SourceSystem(BaseModel):
    name: str
    location: str
    technical_steward: str | None = None


class CriticalMetric(BaseModel):
    term: str
    column: str


class Validation(BaseModel):
    report: str
    business_element: str
    producer: str
    sample: str
    narrative: str
    claimed_sources: list[str] = Field(min_length=1)
    claimed_filters: list[str] = Field(default_factory=list)


class ValueAssumptions(BaseModel):
    people_impacted: int = Field(ge=0)
    hours_saved_per_person: float = Field(ge=0)
    cost_per_hour: float = Field(ge=0)
    issues_identified: int = Field(ge=0)
    value_per_issue: float = Field(ge=0)
    errors_avoided: int = Field(ge=0)
    value_per_error: float = Field(ge=0)
    annual_cost: float = Field(gt=0)

    @property
    def benefits(self) -> dict[str, float]:
        return {
            "Menos tiempo buscando y entendiendo datos":
                self.people_impacted * self.hours_saved_per_person * self.cost_per_hour,
            "Incidencias de datos localizadas antes": self.issues_identified * self.value_per_issue,
            "Errores evitados en cambios": self.errors_avoided * self.value_per_error,
        }

    @property
    def roi(self) -> float:
        return (sum(self.benefits.values()) - self.annual_cost) / self.annual_cost


class LineageInput(BaseModel):
    source_systems: dict[str, SourceSystem]
    critical_metrics: list[CriticalMetric]
    validation: Validation
    value: ValueAssumptions


# --- Navegación ------------------------------------------------------------------------

def upstream(g: nx.DiGraph, column: str) -> set[str]:
    return nx.ancestors(g, column) if column in g else set()


def downstream(g: nx.DiGraph, column: str) -> set[str]:
    return nx.descendants(g, column) if column in g else set()


def roots(g: nx.DiGraph, column: str) -> set[str]:
    """Columnas de origen (sin antecesores) de las que depende una columna."""
    return {n for n in upstream(g, column) if g.in_degree(n) == 0}


def path_to(g: nx.DiGraph, column: str) -> nx.DiGraph:
    """Subgrafo con todo lo que alimenta a una columna (para dibujarlo)."""
    return g.subgraph(upstream(g, column) | {column})


@dataclass(frozen=True)
class Impact:
    column: str
    affected: list[str]
    tables: list[str]
    critical: list[str]  # métricas críticas afectadas


def impact(g: nx.DiGraph, column: str, critical: list[CriticalMetric]) -> Impact:
    """¿Qué se rompe si cambia esta columna?"""
    affected = sorted(downstream(g, column))
    return Impact(column, affected, sorted({a.rsplit(".", 1)[0] for a in affected}),
                  [m.term for m in critical if m.column in affected])


# --- Validación (7 pasos del capítulo) ------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    actual_sources: list[str]
    confirmed: list[str]
    claimed_not_used: list[str]  # la narrativa los cita, pero el linaje no pasa por ellos
    undocumented: list[str]      # el linaje los usa, pero la narrativa no los menciona
    filters_found: list[str]
    filters_missing: list[str]
    actual_filters: list[str]

    @property
    def gaps(self) -> int:
        return len(self.claimed_not_used) + len(self.undocumented) + len(self.filters_missing)


def validate(g: nx.DiGraph, steps: list[TableStep], v: Validation) -> ValidationResult:
    actual = sorted(roots(g, v.business_element))
    involved = {n.rsplit(".", 1)[0] for n in upstream(g, v.business_element)}
    involved.add(v.business_element.rsplit(".", 1)[0])
    filters = [f for s in steps if s.target in involved for f in s.filters]
    text = " ".join(filters).lower()
    return ValidationResult(
        actual_sources=actual,
        confirmed=[c for c in v.claimed_sources if c in actual],
        claimed_not_used=[c for c in v.claimed_sources if c not in actual],
        undocumented=[a for a in actual if a not in v.claimed_sources],
        filters_found=[f for f in v.claimed_filters if f.lower() in text],
        filters_missing=[f for f in v.claimed_filters if f.lower() not in text],
        actual_filters=filters,
    )


# --- Hallazgos ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reach:
    table: str
    reaching: list[str]
    not_reaching: list[str]

    @property
    def rate(self) -> float:
        total = len(self.reaching) + len(self.not_reaching)
        return len(self.reaching) / total if total else 0.0


def reach_curated(g: nx.DiGraph, raw_columns: list[str]) -> list[Reach]:
    """Por tabla raw: qué columnas acaban alimentando la capa curated y cuáles no."""
    by_table: dict[str, tuple[list[str], list[str]]] = {}
    for c in raw_columns:
        hit = any(d.startswith("curated.") for d in downstream(g, c))
        reaching, missing = by_table.setdefault(c.rsplit(".", 1)[0], ([], []))
        (reaching if hit else missing).append(c.rsplit(".", 1)[1])
    return [Reach(t, r, m) for t, (r, m) in sorted(by_table.items())]


def pii_reaching(g: nx.DiGraph, pii_columns: list[str], layer: str = "curated") -> list[tuple]:
    """(columna PII, columna de la capa indicada a la que llega su contenido)."""
    out = []
    for c in pii_columns:
        for d in sorted(downstream(g, c)):
            if d.startswith(f"{layer}."):
                out.append((c, d))
    return out


def maturity_metrics(edges: list[Edge], g: nx.DiGraph, systems: dict[str, SourceSystem],
                     critical: list[CriticalMetric], documented: set[str],
                     curated_tables: list[str]) -> list[tuple[str, int, int]]:
    """Métricas de madurez de los metadatos técnicos (lista del capítulo)."""
    raw_tables = sorted({e.target_table for e in edges if e.kind == "carga"})
    targets = {e.target_table for e in edges}
    complete = [m for m in critical if roots(g, m.column)
                and all(r.startswith("raw.") for r in roots(g, m.column))]
    return [
        ("Fuentes con esquema documentado", sum(t in documented for t in raw_tables),
         len(raw_tables)),
        ("Sistemas de origen con steward técnico",
         sum(bool(s.technical_steward) for s in systems.values()), len(systems)),
        ("Tablas curated con linaje", sum(t in targets for t in curated_tables),
         len(curated_tables)),
        ("Métricas críticas con linaje hasta el origen", len(complete), len(critical)),
    ]
