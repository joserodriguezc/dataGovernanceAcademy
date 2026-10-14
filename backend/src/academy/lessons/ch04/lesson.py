"""Lección 4: línea base de madurez de gestión de datos (los 10 pasos).

Misma lógica que chapters/ch04_linea_base_madurez/run.py del laboratorio. Las respuestas se
simulan y la evidencia sale del warehouse que el alumno ha construido; los participantes salen
del equipo de la lección 3.
"""

from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    BarItem,
    BarListBlock,
    CalloutBlock,
    Column,
    DocumentBlock,
    HeatmapBlock,
    HeatmapRow,
    Kpi,
    KpisBlock,
    ResultSection,
    TableBlock,
)
from academy.core.company import DOMAIN_NAMES
from academy.core.dates import add_months
from academy.core.reporting import fmt_num, fmt_pct, render_template
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch03.lesson import TEAM

from .analysis import (
    company_score,
    dimension_scores,
    group_themes,
    self_assessment_bias,
    unit_scores,
    unsupported_scores,
)
from .evidence import dq_checks, evidence_caps, indicators
from .model import DATA_OFFICE, AssessmentInput, MaturityModel
from .survey import participants, simulate_responses

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
UNIT_NAMES = {**DOMAIN_NAMES, DATA_OFFICE: "Oficina de datos"}
SCOPE_LABELS = {"enterprise": "toda la empresa", "pilot": "piloto con un dominio",
                "rolling": "por oleadas de dominios"}
INDICATOR_LABELS = {
    "documented_tables": "Tablas curated documentadas",
    "lineage_coverage": "Tablas curated con linaje",
    "crm_duplicate_phones": "Clientes que comparten teléfono con otro registro",
    "dq_pass_rate": "Controles de calidad superados (media)",
    "dq_worst_check": "Peor control de calidad",
}

INPUT_SPECS = [
    InputSpec("maturity_model", "Modelo de madurez",
              "Niveles (1 a 5) y dimensiones con sus preguntas, al estilo de DAMA.",
              MaturityModel, INPUTS / "maturity_model.yaml"),
    InputSpec("assessment", "Evaluación",
              "Alcance, fases, simulación de respuestas, hallazgos, plan de mejora y "
              "reevaluación.", AssessmentInput, INPUTS / "assessment.yaml"),
]


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    model: MaturityModel = inputs["maturity_model"]
    inp: AssessmentInput = inputs["assessment"]
    inp.check_against(model)
    team = ctx.input_of(3, TEAM)
    dim_names = {d.id: d.name for d in model.dimensions}

    def level_name(score: float) -> str:
        return model.levels[max(model.min_level, min(model.max_level, int(score)))].name

    people = participants(inp, team.functional_roles)
    responses = simulate_responses(inp, model, people)
    scores = dimension_scores(responses)
    with connect(ctx.db_path, read_only=True) as con:
        ind = indicators(con)
        checks = dq_checks(con)
    caps = evidence_caps(ind)
    flags = unsupported_scores(scores, caps)
    biases = self_assessment_bias(responses, inp.bias_threshold)
    themes = group_themes(inp.findings)
    matrix = unit_scores(responses)
    matrix["_mean"] = matrix.mean(axis=1)

    phases, start = [], inp.start_date
    for p in inp.phases:
        phases.append((p, start))
        start += timedelta(weeks=p.weeks or 0)
    next_assessment = add_months(inp.start_date, inp.reassessment.frequency_months)
    covered = {p.theme for p in inp.plan}
    uncovered = [t.name for t in themes if t.priority == 1 and t.name not in covered]
    ordered = sorted(scores.items(), key=lambda kv: kv[1])
    cap_by_dim = {c.dimension: c for c in caps}
    flagged = {f.cap.dimension for f in flags}
    overall = company_score(responses)

    summary: list = [KpisBlock(items=[
        Kpi(label="Madurez de la empresa", value=f"{fmt_num(overall, 2)} de {model.max_level}",
            detail=level_name(overall)),
        Kpi(label="Objetivo", value=f"Nivel {inp.target_level}",
            detail=model.levels[inp.target_level].name),
        Kpi(label="Participantes", value=fmt_num(len(people)),
            detail=f"{fmt_num(len(responses))} respuestas"),
        Kpi(label="Puntuaciones sin respaldo de la evidencia", value=str(len(flags)),
            tone="warning" if flags else "good"),
    ])]
    for p in people:
        if p.fallback:
            summary.append(CalloutBlock(
                tone="warning", title=f"Sin stewards en {UNIT_NAMES[p.unit]}",
                text=f"Se entrevista a {p.name}. Asigna stewards a ese dominio en la lección 3."))

    dims_blocks: list = [
        BarListBlock(
            title="Madurez por dimensión frente al objetivo",
            subtitle=f"De 1 a {model.max_level}. La marca es el objetivo (nivel "
                     f"{inp.target_level}). ✗: la puntuación supera lo que respalda la "
                     "evidencia del warehouse.",
            min_value=1, max_value=model.max_level,
            legend=f"Escala de niveles de 1 a {model.max_level} · la marca vertical es el "
                   "objetivo · ✗ supera lo que respalda la evidencia",
            items=[BarItem(label=dim_names[d], value=s, display=fmt_num(s, 2),
                           target=inp.target_level, ok=False if d in flagged else None,
                           detail=cap_by_dim[d].reason if d in cap_by_dim else None)
                   for d, s in ordered]),
        TableBlock(
            title="Puntuación y evidencia",
            columns=[Column(key="dim", label="Dimensión"),
                     Column(key="score", label="Puntuación", align="right"),
                     Column(key="level", label="Nivel"),
                     Column(key="cap", label="Máximo según la evidencia", align="right"),
                     Column(key="why", label="Por qué")],
            rows=[{"dim": dim_names[d], "score": fmt_num(s, 2), "level": level_name(s),
                   "cap": str(cap_by_dim[d].max_level) if d in cap_by_dim else "—",
                   "why": cap_by_dim[d].reason if d in cap_by_dim else ""}
                  for d, s in ordered]),
        HeatmapBlock(
            title="Puntuación por unidad y dimensión",
            subtitle="Lo agregado esconde diferencias: cada fila es una unidad evaluada",
            columns=[d.short for d in model.dimensions],
            rows=[HeatmapRow(label=UNIT_NAMES[u],
                             values=[round(float(matrix.loc[u, d.id]), 2)
                                     if d.id in matrix.columns else None
                                     for d in model.dimensions])
                  for u in inp.scope.units if u in matrix.index],
            min_value=1, max_value=model.max_level),
    ]
    for b in biases:
        dims_blocks.append(CalloutBlock(
            tone="warning", title=f"Sesgo de autoevaluación: {UNIT_NAMES[b.unit]}",
            text=f"{b.direction.capitalize()}: se puntúa {fmt_num(b.self_avg, 2)} y el taller "
                 f"le da {fmt_num(b.workshop_avg, 2)} ({'+' if b.gap > 0 else ''}"
                 f"{fmt_num(b.gap, 2)})."))

    evidence_blocks = [TableBlock(
        title="Indicadores medidos en el warehouse",
        description="La evidencia objetiva acota lo que dice la encuesta. Mejoran cuando "
                    "ejecutas las lecciones técnicas (6, 7, 8 y 10).",
        columns=[Column(key="ind", label="Indicador"),
                 Column(key="value", label="Valor", align="right")],
        rows=[{"ind": INDICATOR_LABELS.get(k, k), "value": fmt_pct(v, 1)}
              for k, v in ind.items()])]

    plan_blocks: list = [TableBlock(
        title="Plan de mejora",
        columns=[Column(key="initiative", label="Iniciativa"), Column(key="theme", label="Tema"),
                 Column(key="owner", label="Responsable"),
                 Column(key="when", label="Fechas", align="right"),
                 Column(key="target", label="Objetivo")],
        rows=[{"initiative": p.initiative, "theme": p.theme, "owner": p.owner,
               "when": f"{p.start} → {p.end}",
               "target": fmt_pct(p.target, 1) if p.target <= 1 else fmt_num(p.target)}
              for p in inp.plan])]
    if uncovered:
        plan_blocks.append(CalloutBlock(
            tone="warning", title="Temas prioritarios sin iniciativa",
            text=", ".join(uncovered) + ": ningún punto del plan de mejora los cubre."))

    common = {"company": COMPANY, "year": inp.assessment_year, "dim_names": dim_names}
    docs = [
        DocumentBlock(title="Plan de evaluación", filename="assessment_plan.md",
                      markdown=render_template(
                          TEMPLATES, "assessment_plan.md.j2", company=COMPANY, inp=inp,
                          model=model, people=people, phases=phases, unit_names=UNIT_NAMES,
                          domain_names=DOMAIN_NAMES, scope_labels=SCOPE_LABELS)),
        DocumentBlock(title="Informe de madurez", filename="maturity_report.md",
                      markdown=render_template(
                          TEMPLATES, "maturity_report.md.j2", **common, company_score=overall,
                          max_level=model.max_level, target=inp.target_level,
                          levels=model.levels, level_name=level_name, scores=ordered,
                          caps=cap_by_dim, flagged=flagged, flags=flags, themes=themes,
                          plan=inp.plan, chart_name=None)),
        DocumentBlock(title="Resultados internos por unidad", filename="maturity_internal.md",
                      markdown=render_template(
                          TEMPLATES, "maturity_internal.md.j2", **common,
                          communication=inp.communication, dims=[d.id for d in model.dimensions],
                          dim_short={d.id: d.short for d in model.dimensions},
                          matrix=[(u, matrix.loc[u]) for u in inp.scope.units],
                          unit_names=UNIT_NAMES, biases=biases, threshold=inp.bias_threshold,
                          participation=[(u, sum(p.unit == u for p in people),
                                          int((responses.unit == u).sum()))
                                         for u in inp.scope.units])),
        DocumentBlock(title="Plan de mejora", filename="improvement_plan.md",
                      markdown=render_template(
                          TEMPLATES, "improvement_plan.md.j2", **common, plan=inp.plan,
                          total_funding=sum(p.funding_usd for p in inp.plan),
                          uncovered=uncovered, indicators=ind, dq_checks=checks,
                          next_assessment=next_assessment, reassessment=inp.reassessment,
                          success=inp.success_measures)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Madurez por dimensión", blocks=dims_blocks),
        ResultSection(title="Evidencia del warehouse", blocks=evidence_blocks),
        ResultSection(title="Plan de mejora", blocks=plan_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=4, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
