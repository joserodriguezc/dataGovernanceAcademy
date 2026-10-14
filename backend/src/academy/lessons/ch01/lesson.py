"""Lección 1: data equity, caso de negocio, charter, política y EDG Scorecard.

Misma lógica que chapters/ch01_que_es_gobierno_datos/run.py del laboratorio, pero devuelve
bloques de resultado en lugar de escribir archivos.
"""

from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
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
from academy.core.company import CURRENCY_SYMBOL, DOMAIN_NAMES
from academy.core.reporting import fmt_money, fmt_pct, render_template
from academy.lessons.base import InputSpec, LessonContext, LessonDef

from .business_case import BusinessCaseInput, evaluate_business_case
from .charter import ProgramInput, assess_launch, lint_vision
from .equity import DataEquityInput, evaluate_equity
from .policy import POLICY_SECTIONS, PolicyInput
from .scorecard import ScorecardInput, corporate_scorecard, domain_scorecard

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"

INPUT_SPECS = [
    InputSpec("program", "Programa", "Visión, misiones, señales de lanzamiento y glosario.",
              ProgramInput, INPUTS / "program.yaml"),
    InputSpec("data_equity", "Data equity",
              "Activos y pasivos de datos, valorados hoy y en la situación objetivo.",
              DataEquityInput, INPUTS / "data_equity.yaml"),
    InputSpec("business_case", "Caso de negocio",
              "Horizonte, tasa de descuento y las tres opciones de timeline.",
              BusinessCaseInput, INPUTS / "business_case.yaml"),
    InputSpec("policy", "Política", "Contenido de la política de gobierno de datos.",
              PolicyInput, INPUTS / "policy.yaml"),
    InputSpec("scorecard", "Scorecard",
              "Estado de cada dominio y sus sistemas, y las fechas comprometidas.",
              ScorecardInput, INPUTS / "scorecard.yaml"),
]

TONE = {"green": "good", "yellow": "warning", "red": "bad"}


def compute(inputs: dict[str, BaseModel], ctx: LessonContext | None = None) -> list[ResultSection]:
    program: ProgramInput = inputs["program"]
    equity_in: DataEquityInput = inputs["data_equity"]
    bc: BusinessCaseInput = inputs["business_case"]
    policy: PolicyInput = inputs["policy"]
    sc: ScorecardInput = inputs["scorecard"]

    equity = evaluate_equity(equity_in)
    vetted_only = not bc.include_unvetted_benefits
    annual_benefit = equity.annual_benefit(vetted_only=vetted_only)
    results = evaluate_business_case(bc, annual_benefit)
    recommended = next(r for r in results if r.option.id == bc.recommended_option)
    best_npv = max(results, key=lambda r: r.npv)
    vision_issues = lint_vision(program.vision.statement)
    launch = assess_launch(program.launch)
    corporate = corporate_scorecard(sc)
    domains = [
        {"name": DOMAIN_NAMES[d.id], "executive": d.executive, "stewards": d.stewards,
         "metrics": domain_scorecard(sc, d)}
        for d in sc.domains
    ]

    def payback(r) -> str:
        return f"mes {r.payback_month}" if r.payback_month else "fuera del horizonte"

    # Resumen
    summary = [
        KpisBlock(items=[
            Kpi(label="Data equity hoy", value=fmt_money(equity.equity("current")),
                tone="bad" if equity.equity("current") < 0 else "good",
                detail=f"Objetivo: {fmt_money(equity.equity('target'))}"),
            Kpi(label="Beneficio anual en el caso", value=fmt_money(annual_benefit),
                detail="Solo líneas validadas por el negocio" if vetted_only
                else "Incluye líneas sin validar"),
            Kpi(label=f"VAN de la opción recomendada ({recommended.option.name})",
                value=fmt_money(recommended.npv), detail=f"Payback: {payback(recommended)}",
                tone="good" if recommended.npv > 0 else "bad"),
            Kpi(label="Decisión de lanzamiento", value=launch.verdict.upper(),
                tone="good" if launch.verdict == "lanzar" else "warning"),
        ]),
        CalloutBlock(tone="good" if launch.verdict == "lanzar" else "warning",
                     title=f"Decisión: {launch.verdict}", text=launch.rationale),
        CalloutBlock(tone="warning", title="La visión necesita revisión",
                     text=" ".join(vision_issues)) if vision_issues else
        CalloutBlock(tone="good", title="La visión es breve y no usa jerga de datos",
                     text=program.vision.statement),
    ]

    # Caso de negocio
    case_blocks = [
        LineChartBlock(
            title="Flujo de caja neto acumulado por opción",
            subtitle="El punto marca el mes en que se recupera la inversión (payback)",
            x_label="Mes", y_label=f"Millones de {CURRENCY_SYMBOL}", reference_y=0,
            series=[Series(name=r.option.name,
                           points=[(m, round(v / 1e6, 4))
                                   for m, v in enumerate(r.cumulative, start=1)],
                           emphasis=r.option.id == bc.recommended_option) for r in results],
            markers=[Marker(series=r.option.name, x=r.payback_month,
                            y=round(r.cumulative[r.payback_month - 1] / 1e6, 4),
                            label=f"Payback {r.option.name}: mes {r.payback_month}")
                     for r in results if r.payback_month]),
        TableBlock(
            title="Opciones de timeline",
            description=f"Horizonte de {bc.horizon_months} meses, tasa de descuento "
                        f"{fmt_pct(bc.discount_rate_annual)} anual.",
            columns=[Column(key="option", label="Opción"),
                     Column(key="duration", label="Duración", align="right"),
                     Column(key="build", label="Construcción", align="right"),
                     Column(key="npv", label="VAN", align="right"),
                     Column(key="roi", label="ROI", align="right"),
                     Column(key="payback", label="Payback", align="right")],
            rows=[{"option": r.option.name + (" (recomendada)"
                                              if r.option.id == bc.recommended_option else ""),
                   "duration": f"{r.option.duration_months} meses",
                   "build": fmt_money(r.option.build_cost_usd), "npv": fmt_money(r.npv),
                   "roi": fmt_pct(r.roi), "payback": payback(r)} for r in results]),
    ]
    if best_npv.option.id != recommended.option.id:
        case_blocks.append(CalloutBlock(
            tone="warning", title="La opción recomendada no es la de mayor VAN",
            text=f"«{best_npv.option.name}» tiene un VAN de {fmt_money(best_npv.npv)}. "
                 "Explica en el caso de negocio por qué se recomienda otra."))
    if vetted_only and equity.unvetted:
        left_out = sum(ln.benefit for ln in equity.unvetted)
        case_blocks.append(CalloutBlock(
            tone="info", title="Beneficios sin validar fuera del caso",
            text=f"{len(equity.unvetted)} líneas de data equity aún no las ha validado el "
                 f"negocio y quedan fuera: {fmt_money(left_out)} al año."))

    # Data equity
    equity_rows = [
        {"name": ln.name, "kind": "Activo" if ln.kind == "asset" else "Pasivo",
         "domain": DOMAIN_NAMES.get(ln.domain, ln.domain), "current": fmt_money(ln.current),
         "target": fmt_money(ln.target), "benefit": fmt_money(ln.benefit),
         "vetted": ln.vetted_by or "⚠️ sin validar"}
        for ln in sorted(equity.lines, key=lambda ln: ln.benefit, reverse=True)
    ]
    equity_blocks = [TableBlock(
        title="Activos y pasivos de datos",
        description=f"Valoración anual con una hora de trabajo a "
                    f"{fmt_money(equity_in.hourly_rate_usd)}. Ordenado por mejora anual.",
        columns=[Column(key="name", label="Línea"), Column(key="kind", label="Tipo"),
                 Column(key="domain", label="Dominio"),
                 Column(key="current", label="Hoy", align="right"),
                 Column(key="target", label="Objetivo", align="right"),
                 Column(key="benefit", label="Mejora anual", align="right"),
                 Column(key="vetted", label="Validado por")],
        rows=equity_rows)]

    # EDG Scorecard
    scorecard_blocks = [TableBlock(
        title=f"Scorecard corporativo a {sc.as_of.isoformat()}",
        description="Dominios que cumplen cada métrica. En riesgo: vence en menos de "
                    f"{sc.at_risk_days} días sin estar completa.",
        columns=[Column(key="metric", label="Métrica"),
                 Column(key="progress", label="Avance", align="right"),
                 Column(key="due", label="Fecha comprometida", align="right"),
                 Column(key="status", label="Estado")],
        rows=[{"metric": m.label, "progress": f"{m.numerator}/{m.denominator} "
                                              f"({fmt_pct(m.pct)})",
               "due": m.due.isoformat(), "status": m.status_label} for m in corporate])]
    late = [m for m in corporate if m.status != "green"]
    if late:
        scorecard_blocks.append(CalloutBlock(
            tone="bad" if any(m.status == "red" for m in late) else "warning",
            title=f"{len(late)} métricas necesitan atención",
            text="; ".join(f"{m.label} ({m.status_label})" for m in late) + "."))

    # Documentos (las mismas plantillas que el laboratorio)
    docs = [
        DocumentBlock(title="Charter del programa", filename="charter.md",
                      markdown=render_template(
                          TEMPLATES, "charter.md.j2", company=program.company,
                          vision=program.vision, vision_issues=vision_issues,
                          cdao_mission=program.cdao_mission,
                          cdao_principles=program.cdao_principles,
                          program_mission=program.program_mission.statement, launch=launch,
                          drivers=program.launch.drivers,
                          warning_signs=program.launch.warning_signs,
                          glossary=program.glossary)),
        DocumentBlock(title="Data equity", filename="data_equity.md", markdown=render_template(
            TEMPLATES, "data_equity.md.j2", company=program.company, s=equity,
            hourly_rate=equity_in.hourly_rate_usd, domain_names=DOMAIN_NAMES)),
        DocumentBlock(title="Caso de negocio", filename="business_case.md",
                      markdown=render_template(
                          TEMPLATES, "business_case.md.j2", bc=bc, results=results,
                          rec=recommended, annual_benefit=annual_benefit,
                          top_lines=sorted(equity.lines, key=lambda ln: ln.benefit,
                                           reverse=True)[:5],
                          chart_name=None)),
        DocumentBlock(title="Política de gobierno de datos",
                      filename="data_governance_policy.md", markdown=render_template(
                          TEMPLATES, "policy.md.j2", p=policy, sections=POLICY_SECTIONS,
                          glossary=program.glossary)),
        DocumentBlock(title="EDG Scorecard", filename="edg_scorecard.md",
                      markdown=render_template(
                          TEMPLATES, "edg_scorecard.md.j2", company=program.company,
                          as_of=sc.as_of, at_risk_days=sc.at_risk_days, corporate=corporate,
                          updates=sc.updates, domains=domains)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Caso de negocio", blocks=case_blocks),
        ResultSection(title="Data equity", blocks=equity_blocks),
        ResultSection(title="EDG Scorecard", blocks=scorecard_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=1, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml")

