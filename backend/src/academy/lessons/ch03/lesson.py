"""Lección 3: modelo organizativo, equipo, RACI y ritmo del negocio de datos.

Misma lógica que chapters/ch03_equipo_alto_rendimiento/run.py del laboratorio. Usa el caso de
negocio y el scorecard de la lección 1 tal como los haya dejado el alumno.
"""

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
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
from academy.core.reporting import fmt_money, render_template
from academy.lessons.base import InputSpec, LessonContext, LessonDef
from academy.lessons.ch01.lesson import INPUT_SPECS as CH01_INPUTS

from .org_model import (
    MODEL_LABELS,
    RESPONSIBILITIES,
    RESPONSIBILITY_MATRIX,
    OrgContext,
    recommend_model,
)
from .raci import RaciInput, idle_roles, raci_table
from .rhythm import ForumsInput, build_calendar, forum_issues, portfolio_without_outcome
from .team import (
    FUNCTION_LABELS,
    MAX_LEVEL,
    STATUS_LABELS,
    TeamInput,
    hiring_order_issues,
    org_chart_mermaid,
    skill_gaps,
    team_cost,
)

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
FACT_LABELS = {
    "has_data_capabilities": "Existen requisitos o capacidades de datos",
    "capabilities_consistent": "Las capacidades se implementan de forma consistente",
    "major_trust_issues": "Hay problemas graves de calidad, uso o confianza",
    "broad_support": "Hay apoyo general a la iniciativa de datos",
    "strong_bu_leaders": "Hay líderes de datos fuertes en las áreas",
    "central_office_strong": "La oficina del CDO es sólida y está bien financiada",
}
AI_STATUS = {"open": "🔴 Abierta", "in_progress": "🟡 En curso", "answered": "🟢 Respondida"}
LEVEL_LABELS = {"c_suite": "comité de dirección", "c_minus_1_2": "1-2 niveles por debajo",
                "team": "equipo del CDAO", "mixed": "mixto"}
TYPE_LABELS = {"program": "Programa", "project": "Proyecto", "bau": "Recurrente"}
RAG_LABELS = {"green": "🟢 En plazo", "yellow": "🟡 En riesgo", "red": "🔴 Bloqueado"}
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]

TEAM = InputSpec("team", "Equipo",
                 "Roles del equipo de datos, roles funcionales por dominio (ejecutivo y "
                 "stewards), habilidades y plan de talento.",
                 TeamInput, INPUTS / "team.yaml")
INPUT_SPECS = [
    InputSpec("org_context", "Contexto",
              "Resultados que persigue la empresa, hechos de la organización que deciden el "
              "modelo y gobierno de la IA.", OrgContext, INPUTS / "org_context.yaml"),
    TEAM,
    InputSpec("raci", "RACI", "Quién es responsable (A), quién ejecuta (R), a quién se "
              "consulta (C) y a quién se informa (I) en cada actividad.",
              RaciInput, INPUTS / "raci.yaml"),
    InputSpec("forums", "Ritmo", "Foros de gobierno, su cadencia y el portfolio de iniciativas.",
              ForumsInput, INPUTS / "forums.yaml"),
]


def compute(inputs: dict[str, BaseModel], ctx: LessonContext | None = None) -> list[ResultSection]:
    ctx = ctx or LessonContext()
    org: OrgContext = inputs["org_context"]
    team: TeamInput = inputs["team"]
    raci: RaciInput = inputs["raci"]
    forums: ForumsInput = inputs["forums"]
    specs = {s.id: s for s in CH01_INPUTS}
    ch1_case = ctx.input_of(1, specs["business_case"])
    ch1_scorecard = ctx.input_of(1, specs["scorecard"])

    rec = recommend_model(org.org_facts)
    cost = team_cost(team.roles)
    option = next(o for o in ch1_case.options if o.id == ch1_case.recommended_option)
    annual_budget = option.build_cost_usd / option.duration_months * 12
    hiring_issues = hiring_order_issues(team.roles)
    ch1_execs = {d.id: d.executive for d in ch1_scorecard.domains}
    exec_diffs = [
        f"{DOMAIN_NAMES[f.domain]}: la lección 1 tiene "
        f"«{ch1_execs.get(f.domain) or 'sin ejecutivo'}» y aquí se propone «{f.executive}»."
        for f in team.functional_roles if ch1_execs.get(f.domain) != f.executive
    ]
    gaps = skill_gaps(team.skills)
    names = {f.id: f.name for f in forums.forums}
    by_month: dict[tuple[int, int], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for d, f in build_calendar(forums):
        by_month[(d.year, d.month)][f.id].append(d.strftime("%d"))
    months = [(f"{MONTHS[m - 1].capitalize()} {y}", dict(v)) for (y, m), v in sorted(
        by_month.items())]
    no_outcome = portfolio_without_outcome(forums.portfolio)
    idle = idle_roles(raci)
    issues = forum_issues(forums)
    new_cost = cost["open"] + cost["planned"]

    target = f", y evolucionar a {MODEL_LABELS[rec.target]}" if rec.target != rec.model else ""
    summary: list = [
        KpisBlock(items=[
            Kpi(label="Modelo organizativo", value=MODEL_LABELS[rec.model],
                detail=f"Horizonte: {rec.horizon}"),
            Kpi(label="Coste anual de las posiciones nuevas", value=fmt_money(new_cost),
                detail=f"Presupuesto de la opción «{option.name}» (lección 1): "
                       f"{fmt_money(annual_budget)}/año",
                tone="good" if new_cost <= annual_budget else "bad"),
            Kpi(label="Habilidades por cubrir",
                value=str(sum(g.action != "Cubierta" for g in gaps)),
                detail=f"de {len(gaps)} requeridas"),
            Kpi(label="Roles sin responsabilidad en la RACI", value=str(len(idle)),
                tone="warning" if idle else "good"),
        ]),
        CalloutBlock(tone="info", title=f"Por qué {MODEL_LABELS[rec.model]}{target}",
                     text=rec.rationale + (" Antes hay que: " + "; ".join(rec.prerequisites)
                                           + "." if rec.prerequisites else "")),
    ]
    for issue in hiring_issues + exec_diffs:
        summary.append(CalloutBlock(tone="warning", title="Revisa el equipo", text=issue))

    team_blocks: list = [
        TableBlock(
            title="Roles del equipo de datos",
            columns=[Column(key="title", label="Rol"), Column(key="function", label="Función"),
                     Column(key="status", label="Estado"),
                     Column(key="start", label="Incorporación", align="right"),
                     Column(key="hc", label="Personas", align="right"),
                     Column(key="cost", label="Coste anual", align="right")],
            rows=[{"title": r.title, "function": FUNCTION_LABELS[r.function],
                   "status": STATUS_LABELS[r.status], "start": r.start.isoformat(),
                   "hc": str(r.headcount), "cost": fmt_money(r.total_cost)}
                  for r in team.roles]),
        TableBlock(
            title="Roles funcionales por dominio",
            description="El negocio es dueño de sus datos: cada dominio necesita un ejecutivo y "
                        "stewards de negocio y técnicos.",
            columns=[Column(key="domain", label="Dominio"),
                     Column(key="exec", label="Ejecutivo"),
                     Column(key="business", label="Stewards de negocio"),
                     Column(key="technical", label="Stewards técnicos"),
                     Column(key="gaps", label="Falta")],
            rows=[{"domain": DOMAIN_NAMES[f.domain], "exec": f.executive or "—",
                   "business": ", ".join(f.business_stewards) or "—",
                   "technical": ", ".join(f.technical_stewards) or "—",
                   "gaps": ", ".join(f.gaps) or "✓"} for f in team.functional_roles]),
        HeatmapBlock(
            title="Nivel de habilidades del equipo de datos (0-4)",
            subtitle="Más oscuro = más nivel · entre paréntesis, el nivel objetivo",
            columns=[f"{s} (obj. {req})" for s, req in team.skills.required.items()],
            rows=[HeatmapRow(label=m.name, values=[m.levels[s] for s in team.skills.required])
                  for m in team.skills.members],
            min_value=0, max_value=MAX_LEVEL),
        TableBlock(
            title="Qué hacer con cada habilidad",
            columns=[Column(key="skill", label="Habilidad"),
                     Column(key="req", label="Objetivo", align="right"),
                     Column(key="best", label="Mejor nivel", align="right"),
                     Column(key="at", label="Personas en objetivo", align="right"),
                     Column(key="action", label="Acción")],
            rows=[{"skill": g.skill, "req": str(g.required), "best": str(g.best),
                   "at": str(g.at_target), "action": g.action} for g in gaps]),
    ]

    raci_blocks: list = [TableBlock(
        title="Matriz RACI",
        description="A: responde del resultado (uno solo) · R: ejecuta · C: se le consulta · "
                    "I: se le informa.",
        columns=[Column(key="activity", label="Actividad"),
                 *[Column(key=rid, label=name) for rid, name in raci.roles.items()]],
        rows=[{"activity": row[0], **dict(zip(raci.roles, row[1:], strict=True))}
              for row in raci_table(raci)])]
    if idle:
        raci_blocks.append(CalloutBlock(
            tone="warning", title="Roles que solo opinan o se enteran",
            text=", ".join(idle) + ": no son responsables ni ejecutan ninguna actividad. "
                 "¿Sobran en el equipo o falta asignarles algo?"))

    rhythm_blocks: list = [TableBlock(
        title="Foros de gobierno",
        columns=[Column(key="name", label="Foro"), Column(key="purpose", label="Propósito"),
                 Column(key="chair", label="Preside"), Column(key="level", label="Nivel"),
                 Column(key="first", label="Primera reunión", align="right")],
        rows=[{"name": f.name, "purpose": f.purpose, "chair": f.chair,
               "level": LEVEL_LABELS[f.member_level], "first": f.first_meeting.isoformat()}
              for f in forums.forums])]
    for issue in issues:
        rhythm_blocks.append(CalloutBlock(tone="warning", title="Revisa los foros", text=issue))
    for item in no_outcome:
        rhythm_blocks.append(CalloutBlock(
            tone="warning", title=f"Iniciativa sin resultado para el negocio: {item.name}",
            text="Cada iniciativa del portfolio debe decir qué resultado consigue para su "
                 "stakeholder."))

    docs = [
        DocumentBlock(title="Modelo organizativo", filename="org_model.md",
                      markdown=render_template(
                          TEMPLATES, "org_model.md.j2", company=COMPANY, ctx=org, rec=rec,
                          model_labels=MODEL_LABELS, responsibilities=RESPONSIBILITIES,
                          matrix=RESPONSIBILITY_MATRIX, ai_status=AI_STATUS,
                          facts=[(FACT_LABELS[k], v)
                                 for k, v in org.org_facts.model_dump().items()])),
        DocumentBlock(title="Diseño del equipo", filename="team_design.md",
                      markdown=render_template(
                          TEMPLATES, "team_design.md.j2", company=COMPANY,
                          org_chart=org_chart_mermaid(team.roles), roles=team.roles,
                          function_labels=FUNCTION_LABELS, status_labels=STATUS_LABELS,
                          cost=cost, annual_budget=annual_budget,
                          budget_option=option.name.lower(), hiring_issues=hiring_issues,
                          functional=team.functional_roles, domain_names=DOMAIN_NAMES,
                          exec_diffs=exec_diffs, gaps=gaps, chart_name=None,
                          talent=team.talent_plan)),
        DocumentBlock(title="Matriz RACI", filename="raci.md", markdown=render_template(
            TEMPLATES, "raci.md.j2", company=COMPANY, roles=raci.roles,
            rows=raci_table(raci), idle=idle)),
        DocumentBlock(title="Ritmo del negocio de datos", filename="governance_rhythm.md",
                      markdown=render_template(
                          TEMPLATES, "governance_rhythm.md.j2", company=COMPANY,
                          forums=forums.forums, issues=issues, names=names,
                          level_labels=LEVEL_LABELS,
                          calendar_label=f"{forums.calendar.start.year}", months=months,
                          portfolio=forums.portfolio, type_labels=TYPE_LABELS,
                          status_labels=RAG_LABELS, no_outcome=no_outcome)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Equipo y habilidades", blocks=team_blocks),
        ResultSection(title="RACI", blocks=raci_blocks),
        ResultSection(title="Ritmo", blocks=rhythm_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=3, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml")
