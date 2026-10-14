"""Seguimiento (pasos 6-8): progreso de entregables, resultados de datos y de negocio."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

from .framework import DataOutcomeMetric, Deliverable, Outcome, OutcomeFramework

Status = Literal["green", "yellow", "red"]
STATUS_LABELS = {"green": "🟢 En plazo", "yellow": "🟡 En riesgo", "red": "🔴 Retrasado"}


@dataclass(frozen=True)
class DataOutcomeStatus:
    name: str
    deliverables: list[Deliverable]
    metric: DataOutcomeMetric | None
    measured: float | None  # valor medido en el warehouse, si tiene indicador

    @property
    def delivered(self) -> bool:
        return all(d.complete for d in self.deliverables)

    @property
    def achieved(self) -> bool:
        """Logrado si sus entregables están completos y, si se mide, cumple el objetivo."""
        if self.metric is None or self.measured is None:
            return self.delivered
        if self.metric.higher_is_better:
            return self.measured >= self.metric.target
        return self.measured <= self.metric.target


def data_outcomes(o: Outcome, fw: OutcomeFramework,
                  indicators: dict[str, float]) -> list[DataOutcomeStatus]:
    names = list(dict.fromkeys(d.data_outcome for d in o.deliverables if d.data_outcome))
    out = []
    for name in names:
        metric = fw.data_outcome_metrics.get(name)
        measured = indicators.get(metric.indicator) if metric else None
        out.append(DataOutcomeStatus(
            name, [d for d in o.deliverables if d.data_outcome == name], metric, measured))
    return out


def expected_progress(d: Deliverable, as_of: date) -> float:
    """Avance esperado a la fecha de corte si el trabajo fuera lineal."""
    if as_of <= d.start:
        return 0.0
    if as_of >= d.due:
        return 1.0
    return (as_of - d.start).days / (d.due - d.start).days


def outcome_status(o: Outcome, as_of: date) -> Status:
    """Rojo si hay entregables vencidos; amarillo si se va por detrás de lo esperado."""
    if any(d.overdue(as_of) for d in o.deliverables):
        return "red"
    expected = sum(expected_progress(d, as_of) * d.total for d in o.deliverables)
    done = sum(d.done for d in o.deliverables)
    return "yellow" if done < expected - 0.5 else "green"


def due_in(o: Outcome, start: date, end: date) -> list[Deliverable]:
    """Entregables pendientes con fecha dentro de [start, end]."""
    return [d for d in o.deliverables if not d.complete and start <= d.due <= end]


def completed_by(o: Outcome, as_of: date) -> list[Deliverable]:
    return [d for d in o.deliverables if d.complete and d.due <= as_of]
