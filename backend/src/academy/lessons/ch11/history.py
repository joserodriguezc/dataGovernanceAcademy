"""Historial simulado de operaciones: noches del pipeline y tickets del equipo.

En un caso real saldría del orquestador y del sistema de tickets. Aquí se simula con una
semilla para que el informe tenga meses de datos con los que medir SLAs y causas raíz.
"""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from .config import PROCESS_FAILURE, OpsConfig


def simulate_nights(cfg: OpsConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Una fila por noche y paso: minutos, estado y hora de fin."""
    h, rows = cfg.history, []
    first = cfg.as_of - timedelta(days=h.nights)
    for n in range(h.nights):
        night = first + timedelta(days=n)
        clock = datetime.combine(night, cfg.delivery.start)
        status: dict[str, str] = {}
        for step in cfg.pipeline:
            if any(status.get(d) != "ok" for d in step.depends_on):
                status[step.id] = "omitido"
                rows.append({"night": night, "step": step.id, "minutes": 0.0,
                             "status": "omitido", "finished_at": clock})
                continue
            minutes = step.baseline_minutes * float(rng.lognormal(0, h.duration_noise))
            failed = rng.random() < step.failure_rate
            if failed:  # reintento: vuelve a tardar y solo arregla los fallos transitorios
                minutes += step.baseline_minutes * float(rng.lognormal(0, h.duration_noise))
                failed = rng.random() >= h.retry_success
            clock += timedelta(minutes=minutes)
            status[step.id] = "fallido" if failed else "ok"
            rows.append({"night": night, "step": step.id, "minutes": round(minutes, 1),
                         "status": status[step.id], "finished_at": clock})
    return pd.DataFrame(rows)


def simulate_tickets(cfg: OpsConfig, nights: pd.DataFrame,
                     rng: np.random.Generator) -> pd.DataFrame:
    """Tickets por causa raíz; los fallos de proceso salen de las noches fallidas."""
    h = cfg.history
    first = cfg.as_of - timedelta(days=h.nights)
    events: list[tuple[date, str]] = [
        (row.night, PROCESS_FAILURE) for row in nights[nights.status == "fallido"].itertuples()]
    for cause, per_year in h.tickets_per_year.items():
        for _ in range(int(rng.poisson(per_year * h.nights / 365))):
            events.append((first + timedelta(days=int(rng.integers(0, h.nights))), cause))
    events.sort()
    rows = []
    for i, (opened, cause) in enumerate(events, start=1):
        hours = float(rng.gamma(2.0, h.hours_per_ticket[cause] / 2.0))
        days = int(rng.integers(0, 8)) if cause != PROCESS_FAILURE else int(rng.integers(0, 2))
        resolved = opened + timedelta(days=days)
        rows.append({
            "ticket": f"OPS-{i:04d}", "opened": opened, "cause": cause,
            "system": str(rng.choice(h.systems, p=h.system_weights)),
            "hours": round(hours, 1), "days_to_resolve": days,
            "status": "abierto" if resolved > cfg.as_of else "resuelto",
        })
    return pd.DataFrame(rows)
