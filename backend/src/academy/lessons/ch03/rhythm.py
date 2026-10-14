"""Ritmo del negocio de datos: cartas de los foros, calendario e inventario del portfolio."""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from academy.core.dates import add_months


class Every(BaseModel):
    weeks: int | None = Field(None, gt=0)
    months: int | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _exactly_one(self) -> "Every":
        if (self.weeks is None) == (self.months is None):
            raise ValueError("indica la cadencia en semanas o en meses, no ambas")
        return self

    @property
    def label(self) -> str:
        if self.weeks:
            return "semanal" if self.weeks == 1 else f"cada {self.weeks} semanas"
        return {1: "mensual", 3: "trimestral", 6: "semestral", 12: "anual"}.get(
            self.months or 0, f"cada {self.months} meses")


class Forum(BaseModel):
    id: str
    name: str
    purpose: str
    importance: str
    chair: str
    member_level: Literal["c_suite", "c_minus_1_2", "team", "mixed"]
    members: list[str] = Field(min_length=1)
    responsibilities: list[str] = Field(min_length=1)
    reports_to: str | None
    first_meeting: date
    every: Every
    communication: list[str]
    evaluation: str


class PortfolioItem(BaseModel):
    name: str
    type: Literal["program", "project", "bau"]
    team: str
    stakeholder: str
    stakeholder_outcome: str | None
    status: Literal["green", "yellow", "red"]
    next_milestone: str | None
    blockers: str | None


class CalendarWindow(BaseModel):
    start: date
    months: int = Field(gt=0)


class ForumsInput(BaseModel):
    calendar: CalendarWindow
    forums: list[Forum] = Field(min_length=1)
    portfolio: list[PortfolioItem]

    @model_validator(mode="after")
    def _check_hierarchy(self) -> "ForumsInput":
        ids = {f.id for f in self.forums}
        for f in self.forums:
            if f.reports_to and f.reports_to not in ids:
                raise ValueError(f"{f.id} reporta a un foro inexistente: {f.reports_to}")
        parents = {f.id: f.reports_to for f in self.forums}
        for f in self.forums:  # sin ciclos: subir por la cadena siempre termina
            seen, node = set(), f.id
            while node:
                if node in seen:
                    raise ValueError(f"ciclo en la jerarquía de foros desde {f.id}")
                seen.add(node)
                node = parents[node]
        return self


def meeting_dates(forum: Forum, start: date, end: date) -> list[date]:
    """Fechas de reunión del foro dentro de [start, end)."""
    dates, n = [], 0
    while True:
        if forum.every.weeks:
            d = forum.first_meeting + timedelta(weeks=forum.every.weeks * n)
        else:
            d = add_months(forum.first_meeting, (forum.every.months or 0) * n)
        if d >= end:
            return dates
        if d >= start:
            dates.append(d)
        n += 1


def build_calendar(inp: ForumsInput) -> list[tuple[date, Forum]]:
    end = add_months(inp.calendar.start, inp.calendar.months)
    events = [(d, f) for f in inp.forums for d in meeting_dates(f, inp.calendar.start, end)]
    return sorted(events, key=lambda e: e[0])


def forum_issues(inp: ForumsInput) -> list[str]:
    """Incoherencias con el capítulo en la composición de los foros."""
    issues = []
    for f in inp.forums:
        top = f.reports_to is None
        if top and f.member_level != "c_suite":
            issues.append(f"{f.name} es el foro superior pero no está formado por el comité de "
                          "dirección.")
    return issues


def portfolio_without_outcome(items: list[PortfolioItem]) -> list[PortfolioItem]:
    """Trabajo sin un resultado para el stakeholder: hay que definirlo o cuestionarlo."""
    return [i for i in items if not i.stakeholder_outcome]
