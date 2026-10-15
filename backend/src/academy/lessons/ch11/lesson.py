"""Lección 11: operaciones de datos (pipeline orquestado, SLAs, tickets y valor).

Misma lógica que chapters/ch11_operaciones_datos/run.py del laboratorio. Al ejecutarla corre
el pipeline nocturno de verdad: recarga el warehouse y ejecuta las lecciones 10, 6, 7 y 8 con
las entradas del alumno, y lo registra en una base de operaciones que sobrevive a cada
reconstrucción. El historial de meses (SLAs y tickets) es simulado.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from academy.blocks import (
    BarItem,
    BarListBlock,
    CalloutBlock,
    Column,
    DocumentBlock,
    Kpi,
    KpisBlock,
    LineChartBlock,
    Marker,
    ResultSection,
    Series,
    TableBlock,
)
from academy.core.reporting import fmt_money, fmt_num, fmt_pct, render_template
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef

from .analysis import hotspots, last_runs, root_causes, row_count_changes, sla_summary, value_stream
from .config import OpsConfig
from .history import simulate_nights, simulate_tickets
from .pipeline import lesson_steps, ops_connect, run_pipeline

LESSON_DIR = Path(__file__).parent
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
STATUS_LABELS = {"ok": "✅ Correcto", "fallido": "❌ Fallido", "omitido": "⏭ Omitido"}
PROPOSALS = {
    "Bugs": "Pruebas automáticas en el SDLC (revisión de la lección 9) antes de desplegar",
    "Calidad de datos": "Regla de calidad en origen (lección 8) en lugar de corregir después",
    "Fallos de proceso": "Alerta temprana y reintento automático del paso",
    "Petición de datos ad hoc": "Publicar el dataset en el marketplace (lección 6)",
}

INPUT_SPECS = [
    InputSpec("operations", "Operaciones",
              "Pasos del pipeline con su SLA, entrega de la cifra de ventas, historial "
              "simulado, automatizaciones y reparto entre TI y datos.",
              OpsConfig, LESSON_DIR / "inputs" / "operations.yaml"),
]


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    cfg: OpsConfig = inputs["operations"]
    run_id, status = run_pipeline(cfg.pipeline, ctx.db_path, ctx.raw_dir, ctx.ops_db,
                                  functions=lesson_steps(ctx))

    rng = np.random.default_rng(cfg.history.seed)
    nights = simulate_nights(cfg, rng)
    tickets = simulate_tickets(cfg, nights, rng)
    sla = sla_summary(cfg, nights)
    causes = root_causes(tickets)
    with ops_connect(ctx.ops_db) as ops:
        last, total_runs = last_runs(ops)
        changes = row_count_changes(ops, cfg.row_count_tolerance) if total_runs else None
    with connect(ctx.db_path, read_only=True) as con:
        latest_sale = con.execute("SELECT max(sale_date) FROM curated.fct_sales").fetchone()[0]
    last_by_step = {r.step: {"status": r.status, "attempts": r.attempts, "seconds": r.seconds,
                             "executed_by": r.executed_by,
                             "label": f"{STATUS_LABELS[r.status]} · {fmt_num(r.seconds, 1)} s"}
                    for r in last.itertuples()}
    value = value_stream(cfg)
    names = {s.id: s.name for s in cfg.pipeline}
    failed = [s for s, v in status.items() if v != "ok"]
    freshness = (cfg.as_of - latest_sale).days

    summary: list = [KpisBlock(items=[
        Kpi(label="Pipeline de esta ejecución",
            value="✅ Correcto" if not failed else f"❌ {len(failed)} pasos sin terminar",
            detail=f"Ejecución {run_id} · {total_runs} registradas",
            tone="good" if not failed else "bad"),
        Kpi(label="Noches sin fallos (historial)", value=fmt_pct(sla.success_rate, 1),
            detail=f"Objetivo {fmt_pct(cfg.delivery.success_target)}",
            tone="good" if sla.success_rate >= cfg.delivery.success_target else "warning"),
        Kpi(label="Entregas a tiempo", value=fmt_pct(sla.on_time_rate, 1),
            detail=f"Cifra de ventas lista antes de las {cfg.delivery.ready_by:%H:%M}"),
        Kpi(label="Valor de las automatizaciones", value=fmt_money(value.dollars),
            detail=f"{fmt_num(value.hours)} horas y {value.risks} riesgos evitados al año"),
    ])]
    if freshness > cfg.delivery.freshness_days:
        summary.append(CalloutBlock(
            tone="warning", title="La cifra de ventas no está al día",
            text=f"El último dato de ventas es del {latest_sale:%d/%m/%Y}: {freshness} días, "
                 f"más de los {cfg.delivery.freshness_days} que permite el SLA (regla DQ-16)."))
    summary.append(CalloutBlock(
        tone="info", title="El pipeline ha ejecutado otras lecciones",
        text="Ha recargado el warehouse y ejecutado las lecciones 10, 6, 7 y 8 con tus "
             "entradas. Sus resultados en el warehouse están al día; para ver sus informes, "
             "vuelve a ejecutarlas."))

    pipeline_blocks: list = [TableBlock(
        title=f"Ejecución {run_id}",
        description="Si un paso falla se reintenta una vez; si vuelve a fallar, los que "
                    "dependen de él se omiten.",
        columns=[Column(key="step", label="Paso"), Column(key="owner", label="Responsable"),
                 Column(key="status", label="Estado"),
                 Column(key="attempts", label="Intentos", align="right"),
                 Column(key="seconds", label="Segundos", align="right"),
                 Column(key="by", label="Ejecutado por")],
        rows=[{"step": names.get(s.id, s.id), "owner": s.owner,
               "status": STATUS_LABELS[last_by_step[s.id]["status"]]
               if s.id in last_by_step else "—",
               "attempts": str(last_by_step.get(s.id, {}).get("attempts", "—")),
               "seconds": fmt_num(last_by_step[s.id]["seconds"], 1)
               if s.id in last_by_step else "—",
               "by": last_by_step.get(s.id, {}).get("executed_by", "—")}
              for s in cfg.pipeline])]
    if changes is not None:
        alerts = changes[changes["alert"]]
        pipeline_blocks.append(TableBlock(
            title="Filas de cada tabla curada frente a la ejecución anterior",
            description=f"Se avisa si cambian más de un {fmt_pct(cfg.row_count_tolerance)}.",
            columns=[Column(key="t", label="Tabla"),
                     Column(key="prev", label="Antes", align="right"),
                     Column(key="cur", label="Ahora", align="right"),
                     Column(key="chg", label="Cambio", align="right"),
                     Column(key="alert", label="Aviso")],
            rows=[{"t": r.table_fqn,
                   "prev": fmt_num(r.previous) if r.previous == r.previous else "—",
                   "cur": fmt_num(r.current),
                   "chg": fmt_pct(r.change, 1) if r.change == r.change else "—",
                   "alert": "⚠️ Revisar" if r.alert else "—"} for r in changes.itertuples()]))
        if len(alerts):
            pipeline_blocks.append(CalloutBlock(
                tone="warning", title="Cambio de volumen inesperado",
                text=", ".join(alerts["table_fqn"]) + ": revisa la carga antes de publicar."))

    per_night = nights.groupby("night").agg(end=("finished_at", "max"),
                                            ok=("status", lambda s: (s == "ok").all()))
    hours = [(e - datetime.combine(n, datetime.min.time())).total_seconds() / 3600
             for n, e in zip(per_night.index, per_night["end"], strict=True)]
    deadline = cfg.delivery.ready_by.hour + cfg.delivery.ready_by.minute / 60
    slas = {s.id: s.sla_minutes for s in cfg.pipeline}
    sla_blocks = [
        LineChartBlock(
            title="Hora de fin del pipeline nocturno",
            subtitle=f"Últimas {len(hours)} noches (historial simulado). La línea es el SLA "
                     f"de las {cfg.delivery.ready_by:%H:%M}; los puntos, noches con fallo.",
            x_label="Noche", y_label="Hora de fin", reference_y=round(deadline, 3),
            reference_label=f"SLA {cfg.delivery.ready_by:%H:%M}", y_format="time",
            series=[Series(name="Hora de fin",
                           points=[(i + 1, round(h, 3)) for i, h in enumerate(hours)])],
            markers=[Marker(series="Hora de fin", x=i + 1, y=round(h, 3),
                            label=f"Noche {i + 1}: fallo", tone="bad")
                     for i, (h, ok) in enumerate(zip(hours, per_night["ok"], strict=True))
                     if not ok][:12]),
        TableBlock(
            title="SLA por paso",
            columns=[Column(key="step", label="Paso"),
                     Column(key="runs", label="Ejecuciones", align="right"),
                     Column(key="p95", label="Duración p95 (min)", align="right"),
                     Column(key="sla", label="SLA (min)", align="right"),
                     Column(key="over", label="Fuera de SLA", align="right"),
                     Column(key="failures", label="Fallos", align="right")],
            rows=[{"step": names.get(step, step), "runs": fmt_num(row["runs"]),
                   "p95": fmt_num(row["p95"], 1), "sla": fmt_num(slas.get(step, 0)),
                   "over": fmt_pct(row["over_sla"], 1), "failures": fmt_num(row["failures"])}
                  for step, row in sla.by_step.iterrows()]),
    ]

    total_tickets = int(causes["tickets"].sum())
    ticket_blocks = [
        BarListBlock(
            title="Causas raíz de los tickets de operaciones de datos",
            min_value=0, max_value=float(causes["tickets"].max()),
            items=[BarItem(label=str(cause), value=float(row.tickets),
                           display=f"{int(row.tickets)} ({fmt_pct(row.tickets / total_tickets)})",
                           detail=PROPOSALS.get(str(cause)))
                   for cause, row in causes.iterrows()],
            legend="Tickets en el historial simulado · pasa el ratón para ver la propuesta"),
        TableBlock(
            title="Dónde se concentran (sistema y causa)",
            columns=[Column(key="system", label="Sistema"), Column(key="cause", label="Causa"),
                     Column(key="tickets", label="Tickets", align="right"),
                     Column(key="hours", label="Horas", align="right")],
            rows=[{"system": r.system, "cause": r.cause, "tickets": str(r.tickets),
                   "hours": fmt_num(r.hours)} for r in hotspots(tickets).itertuples()]),
        TableBlock(
            title="Qué proponer para cada causa",
            columns=[Column(key="cause", label="Causa"), Column(key="p", label="Propuesta")],
            rows=[{"cause": c, "p": p} for c, p in PROPOSALS.items()]),
    ]

    docs = [DocumentBlock(title="Operaciones de datos", filename="data_operations.md",
                          markdown=render_template(
                              TEMPLATES, "data_operations.md.j2", company=COMPANY,
                              as_of=cfg.as_of, value=value, automations=cfg.automations,
                              cost_per_hour=cfg.cost_per_hour, run_id=run_id,
                              total_runs=total_runs, ops_db=ctx.ops_db.name,
                              steps=cfg.pipeline, last=last_by_step,
                              status_labels=STATUS_LABELS, latest_sale=latest_sale,
                              freshness=freshness, delivery=cfg.delivery,
                              row_changes=list(changes.itertuples())
                              if changes is not None else None,
                              tolerance=cfg.row_count_tolerance, sla=sla, timeline_chart=None,
                              tickets=tickets, ticket_hours=tickets["hours"].sum(),
                              open_tickets=int((tickets["status"] == "abierto").sum()),
                              mttr=tickets["days_to_resolve"].mean(), causes_chart=None,
                              causes=list(causes.iterrows()),
                              hotspots=list(hotspots(tickets).itertuples()),
                              proposals=PROPOSALS, partnership=cfg.partnership,
                              visibility=cfg.visibility))]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Pipeline", blocks=pipeline_blocks),
        ResultSection(title="SLA", blocks=sla_blocks),
        ResultSection(title="Tickets", blocks=ticket_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=11, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
