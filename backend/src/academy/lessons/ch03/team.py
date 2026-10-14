"""Diseño de la oficina del CDAO: roles, plan de contratación, roles funcionales y talento."""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from academy.core.company import DATA_DOMAINS

Function = Literal["leadership", "office", "governance_strategy", "data_solutions",
                   "architecture_engineering", "data_operations", "analytics"]
FUNCTION_LABELS: dict[str, str] = {
    "leadership": "Dirección",
    "office": "Oficina del CDAO",
    "governance_strategy": "Gobierno y estrategia de datos",
    "data_solutions": "Soluciones de gestión de datos",
    "architecture_engineering": "Arquitectura e ingeniería de datos",
    "data_operations": "Operaciones de datos",
    "analytics": "Analítica",
}
STATUS_LABELS = {"filled": "✅ Cubierto", "open": "🔎 En búsqueda", "planned": "🗓️ Planificado"}
MAX_LEVEL = 4


class Role(BaseModel):
    id: str
    title: str
    function: Function
    reports_to: str | None
    status: Literal["filled", "open", "planned"]
    start: date
    headcount: int = Field(gt=0)
    annual_cost_usd: float = Field(ge=0)  # coste por persona
    book_priority: int | None = None

    @property
    def total_cost(self) -> float:
        return self.headcount * self.annual_cost_usd


class FunctionalRoles(BaseModel):
    domain: str
    executive: str | None
    business_stewards: list[str]
    technical_stewards: list[str]

    @field_validator("domain")
    @classmethod
    def _known_domain(cls, value: str) -> str:
        if value not in DATA_DOMAINS:
            raise ValueError(f"dominio desconocido '{value}'")
        return value

    @property
    def gaps(self) -> list[str]:
        """Cada dominio necesita un ejecutivo y al menos un steward de negocio y uno técnico."""
        gaps = []
        if not self.executive:
            gaps.append("ejecutivo de dominio")
        if not self.business_stewards:
            gaps.append("steward de negocio")
        if not self.technical_stewards:
            gaps.append("steward técnico")
        return gaps


class Member(BaseModel):
    name: str
    role: str
    levels: dict[str, int]


class Skills(BaseModel):
    required: dict[str, int]
    members: list[Member] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_levels(self) -> "Skills":
        for m in self.members:
            if set(m.levels) != set(self.required):
                raise ValueError(f"{m.name}: hay que valorar exactamente {list(self.required)}")
            if any(not 0 <= v <= MAX_LEVEL for v in m.levels.values()):
                raise ValueError(f"{m.name}: los niveles van de 0 a {MAX_LEVEL}")
        return self


class TalentAction(BaseModel):
    lever: str
    action: str
    owner: str
    due: date


class TeamInput(BaseModel):
    roles: list[Role] = Field(min_length=1)
    functional_roles: list[FunctionalRoles]
    skills: Skills
    talent_plan: list[TalentAction]

    @model_validator(mode="after")
    def _check_structure(self) -> "TeamInput":
        ids = [r.id for r in self.roles]
        dupes = [k for k, n in Counter(ids).items() if n > 1]
        if dupes:
            raise ValueError(f"roles repetidos: {dupes}")
        roots = [r.id for r in self.roles if r.reports_to is None]
        if len(roots) != 1:
            raise ValueError(f"debe haber un único rol raíz y hay {roots}")
        unknown = [r.reports_to for r in self.roles if r.reports_to and r.reports_to not in ids]
        if unknown:
            raise ValueError(f"reports_to apunta a roles inexistentes: {unknown}")
        bad_members = [m.role for m in self.skills.members if m.role not in ids]
        if bad_members:
            raise ValueError(f"miembros con roles inexistentes: {bad_members}")
        return self


def hiring_order_issues(roles: list[Role]) -> list[str]:
    """Líderes pendientes de contratar cuya fecha no respeta el orden del capítulo."""
    pending = sorted((r for r in roles if r.book_priority and r.status != "filled"),
                     key=lambda r: r.book_priority or 0)
    issues = []
    for earlier, later in zip(pending, pending[1:], strict=False):
        if later.start < earlier.start:
            issues.append(f"«{later.title}» empieza antes que «{earlier.title}», "
                          "que el capítulo recomienda contratar primero.")
    return issues


def team_cost(roles: list[Role]) -> dict[str, float]:
    """Coste anual del equipo por estado (cubierto, en búsqueda, planificado)."""
    cost = dict.fromkeys(STATUS_LABELS, 0.0)
    for r in roles:
        cost[r.status] += r.total_cost
    return cost


def org_chart_mermaid(roles: list[Role]) -> str:
    """Organigrama en Mermaid; los roles no cubiertos van con borde discontinuo."""
    lines = ["graph TD"]
    for r in roles:
        label = r.title + (f" ×{r.headcount}" if r.headcount > 1 else "")
        lines.append(f'  {r.id}["{label}"]')
    for r in roles:
        if r.reports_to:
            lines.append(f"  {r.reports_to} --> {r.id}")
    pending = [r.id for r in roles if r.status != "filled"]
    if pending:
        lines.append("  classDef pending stroke-dasharray: 5 5")
        lines.append(f"  class {','.join(pending)} pending")
    return "\n".join(lines)


@dataclass(frozen=True)
class SkillGap:
    skill: str
    required: int
    best: int
    at_target: int  # personas en el nivel objetivo o por encima

    @property
    def action(self) -> str:
        if self.best >= self.required:
            return "Cubierta" if self.at_target >= 2 else "Formar a una segunda persona"
        if self.best == self.required - 1:
            return "Formar (upskilling)"
        return "Contratar o incorporar experiencia externa"


def skill_gaps(skills: Skills) -> list[SkillGap]:
    gaps = []
    for skill, required in skills.required.items():
        levels = [m.levels[skill] for m in skills.members]
        gaps.append(SkillGap(skill, required, max(levels), sum(v >= required for v in levels)))
    return gaps
