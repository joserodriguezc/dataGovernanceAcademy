"""Lección 5: definir el éxito y alinear resultados (los 8 pasos).

Misma lógica que chapters/ch05_exito_y_resultados/run.py del laboratorio. Usa la data equity
de la lección 1, los stakeholders de la lección 2 (tal como los haya dejado el alumno) y los
indicadores del warehouse de la lección 4.
"""

from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    CalloutBlock,
    Column,
    DocumentBlock,
    Kpi,
    KpisBlock,
    MatrixGroup,
    ResultSection,
    TableBlock,
    TimelineBlock,
    TimelineItem,
)
from academy.core.dates import add_months
from academy.core.reporting import fmt_money, fmt_num, fmt_pct, render_template
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch01.equity import EquityLine, evaluate_equity
from academy.lessons.ch01.lesson import INPUT_SPECS as CH01_INPUTS
from academy.lessons.ch02.lesson import STAKEHOLDERS
from academy.lessons.ch04.evidence import indicators

from .framework import BARRIER_LABELS, OutcomeFramework, warnings
from .progress import (
    STATUS_LABELS,
    completed_by,
    data_outcomes,
    due_in,
    expected_progress,
    outcome_status,
)

LESSON_DIR = Path(__file__).parent
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
STATUS_TONES = {"green": "good", "yellow": "warning", "red": "bad"}
SERIES_TONES = ["info", "warning", "good", "bad"]  # solo para distinguir los resultados

INPUT_SPECS = [
    InputSpec("outcomes", "Resultados",
              "Resultados de negocio con su stakeholder, métrica, líneas de data equity, "
              "capacidades y entregables; barreras y revisión trimestral.",
              OutcomeFramework, LESSON_DIR / "inputs" / "outcomes.yaml"),
]


def fmt_metric(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    return {"usd": fmt_money, "pct": fmt_pct}.get(unit, lambda v: fmt_num(v) + (
        " h" if unit == "hours" else ""))(value)


def variance_text(fw: OutcomeFramework, o) -> str:
    overdue = [d for d in o.deliverables if d.overdue(fw.as_of)]
    if overdue:
        return "Entregables vencidos: " + "; ".join(
            f"{d.id} ({d.done} de {d.total}, vencía el {d.due:%d/%m/%Y})" for d in overdue) + "."
    behind = [d for d in o.deliverables
              if d.done < expected_progress(d, fw.as_of) * d.total - 0.5]
    return "Por detrás del ritmo previsto: " + ", ".join(d.id for d in behind) + "."


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    fw: OutcomeFramework = inputs["outcomes"]
    sh = ctx.input_of(2, STAKEHOLDERS)
    equity_spec = next(s for s in CH01_INPUTS if s.id == "data_equity")
    equity = evaluate_equity(ctx.input_of(1, equity_spec))

    lines = {ln.id: ln for ln in equity.lines}
    names = {g.id: g.name for g in sh.groups}
    for o in fw.outcomes:
        if o.stakeholder not in names:
            raise ValueError(f"{o.id}: el stakeholder «{o.stakeholder}» no está en la "
                             "lección 2.")
        missing = set(o.equity_lines) - set(lines)
        if missing:
            raise ValueError(f"{o.id}: líneas de data equity que no existen en la lección 1: "
                             f"{sorted(missing)}")
    equity_by: dict[str, list[EquityLine]] = {
        o.id: [lines[i] for i in o.equity_lines] for o in fw.outcomes}
    value = {oid: sum(ln.benefit for ln in lns) for oid, lns in equity_by.items()}
    warns = warnings(fw) + [
        f"{o.id}: usa la línea {ln.id}, que el negocio aún no ha validado en la lección 1."
        for o in fw.outcomes for ln in equity_by[o.id] if not ln.vetted]

    with connect(ctx.db_path, read_only=True) as con:
        ind = indicators(con)
    summary_rows = []
    for o in fw.outcomes:
        status = outcome_status(o, fw.as_of)
        summary_rows.append({"o": o, "status": status,
                             "data_outcomes": data_outcomes(o, fw, ind),
                             "variance": "" if status == "green" else variance_text(fw, o)})

    horizon = add_months(fw.qbr.quarter_end, 3)
    by_stakeholder = []
    for sid in dict.fromkeys(o.stakeholder for o in fw.outcomes):
        outs = [o for o in fw.outcomes if o.stakeholder == sid]
        by_stakeholder.append({
            "group": sh.by_id(sid), "outcomes": outs,
            "capabilities": [c.name for o in outs for c in o.capabilities],
            "value": sum(value[o.id] for o in outs),
            "actual": [f"{o.business_metric.name}: "
                       f"{fmt_metric(o.business_metric.actual, o.business_metric.unit)}"
                       for o in outs],
            "completed": [d for o in outs for d in completed_by(o, fw.as_of)],
            "next": [d for o in outs for d in due_in(o, fw.as_of + timedelta(days=1), horizon)],
        })

    # Resumen
    red = sum(r["status"] == "red" for r in summary_rows)
    summary: list = [KpisBlock(items=[
        Kpi(label="Resultados de negocio", value=str(len(fw.outcomes))),
        Kpi(label="Valor anual comprometido", value=fmt_money(sum(value.values())),
            detail="Mejora de data equity de la lección 1"),
        Kpi(label="Resultados retrasados", value=str(red), tone="bad" if red else "good"),
        Kpi(label="Avisos de credibilidad", value=str(len(warns)),
            tone="warning" if warns else "good"),
    ])]
    for w in warns:
        summary.append(CalloutBlock(tone="warning", title="Aviso", text=w))

    outcome_blocks: list = [TableBlock(
        title=f"Estado de cada resultado a {fw.as_of:%d/%m/%Y}",
        columns=[Column(key="id", label="Resultado"), Column(key="who", label="Stakeholder"),
                 Column(key="status", label="Estado"),
                 Column(key="progress", label="Hitos", align="right"),
                 Column(key="value", label="Valor anual", align="right"),
                 Column(key="variance", label="Desviación")],
        rows=[{"id": f"{r['o'].id} · {r['o'].business_outcome}", "who": names[r["o"].stakeholder],
               "status": STATUS_LABELS[r["status"]],
               "progress": fmt_pct(r["o"].milestone_progress),
               "value": fmt_money(value[r["o"].id]), "variance": r["variance"] or "—"}
              for r in summary_rows])]
    data_rows = [
        {"outcome": r["o"].id, "name": s.name,
         "measured": fmt_pct(s.measured, 1) if s.measured is not None else "—",
         "target": fmt_pct(s.metric.target, 1) if s.metric else "—",
         "ok": "✅ Logrado" if s.achieved else "⏳ Pendiente"}
        for r in summary_rows for s in r["data_outcomes"]]
    outcome_blocks.append(TableBlock(
        title="Resultados de datos medidos en el warehouse",
        description="Primero se mide el éxito en resultados de datos y después en el negocio. "
                    "Mejoran cuando ejecutas las lecciones técnicas.",
        columns=[Column(key="outcome", label="Resultado"),
                 Column(key="name", label="Resultado de datos"),
                 Column(key="measured", label="Medido", align="right"),
                 Column(key="target", label="Objetivo", align="right"),
                 Column(key="ok", label="Estado")],
        rows=data_rows))

    roadmap = [TimelineBlock(
        title="Roadmap de entregables por resultado de negocio",
        subtitle="Al final de cada barra, los hitos completados sobre el total",
        today=fw.as_of,
        groups=[MatrixGroup(id=o.id, label=f"{o.id} · {names[o.stakeholder]}",
                            tone=SERIES_TONES[i % len(SERIES_TONES)])
                for i, o in enumerate(fw.outcomes)],
        items=[TimelineItem(label=f"{d.id}. {d.name}", group=o.id, start=d.start, end=d.due,
                            note=f"{d.done}/{d.total}" + (" ✓" if d.complete else
                                                          " vencido" if d.overdue(fw.as_of)
                                                          else ""))
               for o in fw.outcomes for c in o.capabilities for d in c.deliverables])]

    barriers = [TableBlock(
        title="Registro de barreras",
        columns=[Column(key="type", label="Barrera"),
                 Column(key="outcomes", label="Resultados"),
                 Column(key="desc", label="Descripción"),
                 Column(key="sev", label="Severidad", align="right"),
                 Column(key="mitigation", label="Mitigación")],
        rows=[{"type": BARRIER_LABELS[b.type], "outcomes": ", ".join(b.outcomes),
               "desc": b.description, "sev": str(b.severity), "mitigation": b.mitigation}
              for b in sorted(fw.barriers, key=lambda b: -b.severity)])]

    common = {"company": COMPANY, "names": names, "fmt": fmt_metric}
    docs = [
        DocumentBlock(title="Marco de resultados", filename="outcome_framework.md",
                      markdown=render_template(
                          TEMPLATES, "outcome_framework.md.j2", **common,
                          outcomes=fw.outcomes, equity=equity_by, value=value)),
        DocumentBlock(title="Informe de progreso", filename="progress_report.md",
                      markdown=render_template(
                          TEMPLATES, "progress_report.md.j2", **common, as_of=fw.as_of,
                          summary=summary_rows, status_labels=STATUS_LABELS,
                          barrier_labels=BARRIER_LABELS, warnings=warns,
                          barriers=sorted(fw.barriers, key=lambda b: -b.severity))),
        DocumentBlock(title="Mapa de valor por stakeholder (QBR)", filename="value_map.md",
                      markdown=render_template(
                          TEMPLATES, "value_map.md.j2", **common, stakeholders=by_stakeholder,
                          qbr=fw.qbr, value=value)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Resultados", blocks=outcome_blocks),
        ResultSection(title="Roadmap", blocks=roadmap),
        ResultSection(title="Barreras", blocks=barriers),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=5, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
