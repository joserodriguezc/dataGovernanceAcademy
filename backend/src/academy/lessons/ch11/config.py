"""Configuración de las operaciones de datos."""

from datetime import date, time

from pydantic import BaseModel, Field, model_validator

PROCESS_FAILURE = "Fallos de proceso"


class Step(BaseModel):
    id: str
    name: str
    depends_on: list[str]
    owner: str
    sla_minutes: float = Field(gt=0)
    baseline_minutes: float = Field(gt=0)
    failure_rate: float = Field(ge=0, le=1)


class Delivery(BaseModel):
    start: time
    ready_by: time
    freshness_days: int = Field(ge=0)
    success_target: float = Field(gt=0, le=1)


class History(BaseModel):
    seed: int
    nights: int = Field(gt=0)
    duration_noise: float = Field(ge=0)
    retry_success: float = Field(ge=0, le=1)
    tickets_per_year: dict[str, float]
    hours_per_ticket: dict[str, float]
    systems: list[str]
    system_weights: list[float]

    @model_validator(mode="after")
    def _check(self) -> "History":
        if not set(self.tickets_per_year) <= set(self.hours_per_ticket):
            raise ValueError("cada causa de tickets_per_year necesita sus hours_per_ticket")
        if PROCESS_FAILURE not in self.hours_per_ticket:
            raise ValueError(f"falta hours_per_ticket de «{PROCESS_FAILURE}»")
        weights_ok = abs(sum(self.system_weights) - 1) <= 1e-6
        if len(self.systems) != len(self.system_weights) or not weights_ok:
            raise ValueError("system_weights debe tener un peso por sistema y sumar 1")
        return self


class Automation(BaseModel):
    name: str
    hours_saved: float = Field(ge=0)
    dollars_saved: float = Field(ge=0)
    risks_avoided: int = Field(ge=0)
    chapter: int


class Partnership(BaseModel):
    activity: str
    it: str
    data: str


class Visibility(BaseModel):
    champion: str
    channels: list[str]


class OpsConfig(BaseModel):
    as_of: date
    pipeline: list[Step] = Field(min_length=1)
    delivery: Delivery
    row_count_tolerance: float = Field(gt=0)
    history: History
    automations: list[Automation]
    cost_per_hour: float = Field(gt=0)
    partnership: list[Partnership]
    visibility: Visibility

    @model_validator(mode="after")
    def _dag(self) -> "OpsConfig":
        seen: set[str] = set()
        for s in self.pipeline:  # orden topológico: cada paso depende de pasos anteriores
            missing = set(s.depends_on) - seen
            if missing:
                raise ValueError(f"{s.id} depende de pasos que no le preceden: {sorted(missing)}")
            seen.add(s.id)
        return self
