"""Métricas de operaciones: SLAs, observabilidad, causas raíz y panel de valor."""

from dataclasses import dataclass
from datetime import datetime

import duckdb
import pandas as pd

from .config import OpsConfig


@dataclass(frozen=True)
class SlaSummary:
    nights: int
    successful: int
    on_time: int
    by_step: pd.DataFrame  # paso -> ejecuciones, % fuera de SLA, p95, fallos

    @property
    def success_rate(self) -> float:
        return self.successful / self.nights

    @property
    def on_time_rate(self) -> float:
        return self.on_time / self.nights


def sla_summary(cfg: OpsConfig, nights: pd.DataFrame) -> SlaSummary:
    per_night = nights.groupby("night").agg(
        ok=("status", lambda s: (s == "ok").all()), end=("finished_at", "max"))
    deadline = per_night.index.map(lambda d: datetime.combine(d, cfg.delivery.ready_by))
    on_time = int((per_night["ok"] & (per_night["end"] <= deadline)).sum())
    sla = {s.id: s.sla_minutes for s in cfg.pipeline}
    ran = nights[nights.status != "omitido"]
    by_step = ran.groupby("step").agg(
        runs=("minutes", "size"), p95=("minutes", lambda m: m.quantile(0.95)),
        failures=("status", lambda s: int((s == "fallido").sum())))
    by_step["over_sla"] = ran.assign(over=ran.apply(
        lambda r: r.minutes > sla[r.step], axis=1)).groupby("step")["over"].mean()
    by_step = by_step.reindex([s.id for s in cfg.pipeline])
    return SlaSummary(len(per_night), int(per_night["ok"].sum()), on_time, by_step)


def last_runs(ops: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, int]:
    """Pasos de la última ejecución real y número total de ejecuciones registradas."""
    total = ops.execute("SELECT count(DISTINCT run_id) FROM runs").fetchone()[0]
    last = ops.execute("""
        SELECT step, max(attempt) AS attempts, sum(seconds) AS seconds,
               arg_max(status, attempt) AS status, max(executed_by) AS executed_by,
               min(started_at) AS started_at
        FROM runs WHERE run_id = (SELECT max(run_id) FROM runs)
        GROUP BY step ORDER BY min(started_at)""").df()
    return last, total


def row_count_changes(ops: duckdb.DuckDBPyConnection, tolerance: float) -> pd.DataFrame:
    """Variación de filas de cada tabla curada entre las dos últimas ejecuciones."""
    df = ops.execute("""
        WITH ranked AS (
            SELECT *, dense_rank() OVER (ORDER BY run_id DESC) AS k FROM row_counts)
        SELECT a.table_fqn, b.row_count AS previous, a.row_count AS current
        FROM ranked a LEFT JOIN ranked b ON a.table_fqn = b.table_fqn AND b.k = 2
        WHERE a.k = 1 ORDER BY 1""").df().astype({"previous": float, "current": float})
    df["change"] = (df["current"] - df["previous"]) / df["previous"]
    df["alert"] = df["change"].abs() > tolerance
    return df


def root_causes(tickets: pd.DataFrame) -> pd.DataFrame:
    return (tickets.groupby("cause").agg(tickets=("ticket", "size"), hours=("hours", "sum"))
            .sort_values("tickets", ascending=False))


def hotspots(tickets: pd.DataFrame, top: int = 5) -> pd.DataFrame:
    """Revisión posterior (after-action review): combinaciones sistema-causa más repetidas."""
    return (tickets.groupby(["system", "cause"]).agg(tickets=("ticket", "size"),
                                                     hours=("hours", "sum"))
            .sort_values(["tickets", "hours"], ascending=False).head(top).reset_index())


@dataclass(frozen=True)
class ValueStream:
    dollars: float
    hours: float
    risks: int
    automations: int


def value_stream(cfg: OpsConfig) -> ValueStream:
    hours = sum(a.hours_saved for a in cfg.automations)
    return ValueStream(
        dollars=sum(a.dollars_saved for a in cfg.automations) + hours * cfg.cost_per_hour,
        hours=hours, risks=sum(a.risks_avoided for a in cfg.automations),
        automations=len(cfg.automations))
