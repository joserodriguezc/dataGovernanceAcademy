"""Bucles de feedback con el comité de datos y comunicación a toda la organización.

Señales del capítulo de que el ritmo o el contenido de las reuniones no funciona:
- Cambia la membresía: los miembros delegan de forma recurrente en su equipo.
- Peticiones fuera de ciclo: piden información entre reuniones, hay que verse más.
- Silencio: no hay preguntas ni peticiones, el contenido no les resulta relevante.
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Attendance = Literal["present", "delegated", "absent"]


class Committee(BaseModel):
    name: str
    cadence_months: int = Field(gt=0)
    members: list[str] = Field(min_length=1)


class Meeting(BaseModel):
    date: date
    attendance: dict[str, Attendance]
    questions: int = Field(ge=0)
    off_cycle_requests: int = Field(ge=0)


class SignalThresholds(BaseModel):
    delegation_window: int = Field(3, gt=0)
    delegation_threshold: int = Field(2, gt=0)
    off_cycle_threshold: int = Field(4, ge=0)
    silence_questions: int = Field(1, ge=0)


class OpenForum(BaseModel):
    name: str
    cadence: str
    audience: str


class Communication(BaseModel):
    capability: str
    can_do_now: str = Field(min_length=1)  # ¿Qué podrá hacer un empleado que hoy no puede?
    why_it_matters: str = Field(min_length=1)  # ¿Por qué le importa?
    channel: str
    date: date


class CoalitionInput(BaseModel):
    committee: Committee
    meetings: list[Meeting] = Field(min_length=1)
    signals: SignalThresholds = SignalThresholds()
    open_forum: OpenForum
    channels: list[str] = Field(min_length=1)
    communications: list[Communication] = Field(default_factory=list)

    @model_validator(mode="after")
    def _attendance_covers_members(self) -> "CoalitionInput":
        members = set(self.committee.members)
        for m in self.meetings:
            if set(m.attendance) != members:
                raise ValueError(f"la asistencia del {m.date} no coincide con los miembros")
        self.meetings.sort(key=lambda m: m.date)
        return self


@dataclass(frozen=True)
class Signal:
    kind: Literal["membership_shift", "off_cycle", "silence"]
    message: str
    action: str


def delegation_counts(meetings: list[Meeting], window: int) -> dict[str, int]:
    """Veces que cada miembro delegó en las últimas `window` reuniones."""
    recent = meetings[-window:]
    members = recent[-1].attendance.keys()
    return {m: sum(mt.attendance[m] == "delegated" for mt in recent) for m in members}


def detect_signals(inp: CoalitionInput) -> list[Signal]:
    t, last = inp.signals, inp.meetings[-1]
    signals = []
    for member, n in delegation_counts(inp.meetings, t.delegation_window).items():
        if n >= t.delegation_threshold:
            signals.append(Signal(
                "membership_shift",
                f"{member} delegó en {n} de las últimas {t.delegation_window} reuniones.",
                f"Reunión 1:1 con {member} para entender qué haría el comité más valioso "
                "para su área.",
            ))
    if last.off_cycle_requests >= t.off_cycle_threshold:
        signals.append(Signal(
            "off_cycle",
            f"{last.off_cycle_requests} peticiones de información fuera de ciclo desde la "
            "última reunión.",
            f"Reducir la cadencia de {inp.committee.cadence_months} a "
            f"{max(1, inp.committee.cadence_months - 1)} meses o enviar una actualización "
            "intermedia.",
        ))
    if last.questions <= t.silence_questions and last.off_cycle_requests == 0:
        signals.append(Signal(
            "silence",
            "Apenas hubo preguntas y no hay peticiones entre reuniones.",
            "Pedir feedback a cada miembro sobre la relevancia del contenido.",
        ))
    return signals
