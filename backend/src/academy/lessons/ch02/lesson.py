"""Lección 2: stakeholders, sponsor ejecutivo y plan de coalición.

Misma lógica que chapters/ch02_coalicion_defensores/run.py del laboratorio.
"""

from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from academy.blocks import (
    CalloutBlock,
    Column,
    DocumentBlock,
    Kpi,
    KpisBlock,
    MatrixBlock,
    MatrixGroup,
    MatrixPoint,
    QuadrantLabel,
    ResultSection,
    TableBlock,
)
from academy.core.company import DOMAIN_NAMES
from academy.core.reporting import render_template
from academy.lessons.base import InputSpec, LessonContext, LessonDef

from .feedback import CoalitionInput, detect_signals
from .sponsors import CRITERIA, SponsorInput, assess_sponsors, pilot_mismatch, recommend
from .stakeholders import (
    DIRECTION_LABELS,
    HEALTH_LABELS,
    HIGH,
    LEVEL_LABELS,
    StakeholderGroup,
    StakeholderInput,
    listening_coverage,
    listening_gaps,
    vanity_groups,
)

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
ATTENDANCE_LABELS = {"present": "✅", "delegated": "↘️ delegó", "absent": "❌"}
SIGNAL_LABELS = {"membership_shift": "Cambio de membresía",
                 "off_cycle": "Peticiones fuera de ciclo", "silence": "Silencio"}
HEALTH_TONES = {"positive": "good", "neutral": "info", "negative": "bad"}
HEALTH_GROUP_LABELS = {"positive": "Relación positiva", "neutral": "Relación neutral",
                       "negative": "Relación negativa"}

STAKEHOLDERS = InputSpec("stakeholders", "Stakeholders",
                         "Grupos de interés con su influencia, interés, salud de la relación y "
                         "mapa de objetivos, más las sesiones de escucha.",
                         StakeholderInput, INPUTS / "stakeholders.yaml")
INPUT_SPECS = [
    STAKEHOLDERS,
    InputSpec("sponsors", "Sponsors",
              "Candidatos a sponsor ejecutivo, pesos de los criterios y caso de negocio piloto.",
              SponsorInput, INPUTS / "sponsors.yaml"),
    InputSpec("coalition", "Coalición",
              "Comité de datos, asistencia a las reuniones, foro abierto y comunicaciones.",
              CoalitionInput, INPUTS / "coalition.yaml"),
]


def _spread(groups: list[StakeholderGroup]) -> dict[str, tuple[float, float]]:
    """Separa los puntos que comparten celda para que no se tapen."""
    cells: dict[tuple[int, int], list[str]] = defaultdict(list)
    for g in groups:
        cells[(g.interest, g.influence)].append(g.id)
    offsets = [(0, 0), (0, -0.28), (0, 0.28), (0, -0.56), (0, 0.56)]
    positions = {}
    for (x, y), ids in cells.items():
        for i, gid in enumerate(ids):
            dx, dy = offsets[i % len(offsets)]
            positions[gid] = (x + dx, y + dy)
    return positions


def compute(inputs: dict[str, BaseModel], ctx: LessonContext | None = None) -> list[ResultSection]:
    sh: StakeholderInput = inputs["stakeholders"]
    sp: SponsorInput = inputs["sponsors"]
    co: CoalitionInput = inputs["coalition"]

    names = {g.id: g.name for g in sh.groups}
    unknown = [c.stakeholder for c in sp.candidates if c.stakeholder not in names]
    if unknown:
        raise ValueError(f"Hay candidatos a sponsor que no están en el registro de "
                         f"stakeholders: {unknown}")

    coverage = listening_coverage(sh.listening_sessions)
    gaps = [DIRECTION_LABELS[d] for d in listening_gaps(sh.listening_sessions)]
    quadrants: dict[str, list[str]] = {q: [] for q in (
        "Gestionar de cerca", "Mantener satisfecho", "Mantener informado", "Monitorizar")}
    for g in sorted(sh.groups, key=lambda g: (-g.influence, -g.interest)):
        quadrants[g.quadrant].append(g.name)
    mapped = [g for g in sh.groups if g.map]
    vanity = vanity_groups(sh.groups)
    assessments = assess_sponsors(sp)
    recommended = recommend(assessments)
    mismatch = pilot_mismatch(sp.pilot_business_case, recommended)
    signals = detect_signals(co)
    partners = [g for g in sh.groups if g.partnership]

    # Resumen
    primary = names[recommended[0].candidate.stakeholder] if recommended else "ninguno"
    summary: list = [KpisBlock(items=[
        Kpi(label="Grupos de stakeholders", value=str(len(sh.groups)),
            detail=f"{len(mapped)} en el mapa de objetivos"),
        Kpi(label="Gestionar de cerca", value=str(len(quadrants["Gestionar de cerca"])),
            detail="Mucha influencia y mucho interés"),
        Kpi(label="Sponsor principal recomendado", value=primary,
            detail=f"{recommended[0].score:.0f}/100" if recommended else None,
            tone="good" if recommended else "bad"),
        Kpi(label="Señales del comité", value=str(len(signals)),
            tone="warning" if signals else "good"),
    ])]
    if gaps:
        summary.append(CalloutBlock(tone="warning", title="Huecos de escucha",
                                    text="Todavía no se ha escuchado en estas direcciones: "
                                         + "; ".join(gaps) + "."))
    for g in vanity:
        summary.append(CalloutBlock(
            tone="warning", title=f"Solo métricas del dato: {g.name}",
            text="Todos sus resultados objetivo miden el dato, ninguno el negocio. Añade al "
                 "menos un resultado de negocio en su mapa."))

    # Stakeholders
    positions = _spread(sh.groups)
    lo, hi = 0.5, 5.5
    stakeholder_blocks = [
        MatrixBlock(
            title=f"Stakeholders de {COMPANY}: influencia e interés",
            subtitle="Color y forma indican la salud de la relación",
            x_label="Interés en el programa (1-5)", y_label="Influencia (1-5)",
            x_range=(lo, hi), y_range=(lo - 0.2, hi + 0.2), ticks=[1, 2, 3, 4, 5],
            divider_x=HIGH + 0.5, divider_y=HIGH + 0.5,
            quadrants=[QuadrantLabel(x=0.6, y=5.6, text="Mantener satisfecho"),
                       QuadrantLabel(x=3.6, y=5.6, text="Gestionar de cerca"),
                       QuadrantLabel(x=0.6, y=0.4, text="Monitorizar"),
                       QuadrantLabel(x=3.6, y=0.4, text="Mantener informado")],
            groups=[MatrixGroup(id=h, label=HEALTH_GROUP_LABELS[h], tone=t)
                    for h, t in HEALTH_TONES.items()],
            points=[MatrixPoint(x=positions[g.id][0], y=positions[g.id][1], label=g.short,
                                group=g.health,
                                detail=f"{g.name} · influencia {g.influence}, interés "
                                       f"{g.interest} · {g.quadrant}")
                    for g in sh.groups]),
        TableBlock(
            title="Registro de stakeholders",
            columns=[Column(key="name", label="Grupo"), Column(key="kind", label="Tipo"),
                     Column(key="level", label="Nivel"), Column(key="quadrant", label="Cuadrante"),
                     Column(key="health", label="Relación"),
                     Column(key="measures", label="Cómo mide el éxito")],
            rows=[{"name": g.name, "kind": "Interno" if g.kind == "internal" else "Externo",
                   "level": LEVEL_LABELS[g.level], "quadrant": g.quadrant,
                   "health": HEALTH_LABELS[g.health], "measures": "; ".join(g.success_measures)}
                  for g in sorted(sh.groups, key=lambda g: (-g.influence, -g.interest))]),
        TableBlock(
            title="Escucha en las cinco direcciones",
            columns=[Column(key="direction", label="Dirección"),
                     Column(key="done", label="Hechas", align="right"),
                     Column(key="planned", label="Planificadas", align="right")],
            rows=[{"direction": DIRECTION_LABELS[d], "done": str(c["done"]),
                   "planned": str(c["planned"])} for d, c in coverage.items()]),
    ]

    # Sponsors
    rec_ids = {a.candidate.stakeholder for a in recommended}
    sponsor_blocks: list = [TableBlock(
        title="Evaluación de candidatos a sponsor",
        description="Puntuación ponderada de 0 a 100. Quien no reporta al CEO, o es el CIO "
                    "(el socio para entregar), queda excluido.",
        columns=[Column(key="name", label="Candidato"),
                 Column(key="domain", label="Dominio"),
                 *[Column(key=k, label=label, align="right") for k, label in CRITERIA.items()],
                 Column(key="score", label="Puntuación", align="right"),
                 Column(key="status", label="Resultado")],
        rows=[{"name": names[a.candidate.stakeholder],
               "domain": DOMAIN_NAMES.get(a.candidate.domain or "", "—"),
               **{k: str(a.candidate.scores.get(k, "—")) for k in CRITERIA},
               "score": f"{a.score:.0f}",
               "status": ("⭐ Recomendado" if a.candidate.stakeholder in rec_ids
                          else a.exclusion or "Elegible")} for a in assessments])]
    if mismatch:
        sponsor_blocks.append(CalloutBlock(tone="warning", title="Piloto y sponsor no encajan",
                                           text=mismatch))

    # Coalición
    coalition_blocks: list = []
    for s in signals:
        coalition_blocks.append(CalloutBlock(
            tone="warning", title=f"Señal: {SIGNAL_LABELS[s.kind]}",
            text=f"{s.message} Acción: {s.action}"))
    if not signals:
        coalition_blocks.append(CalloutBlock(tone="good", title="Sin señales de alerta",
                                             text="El comité asiste y participa con normalidad."))
    coalition_blocks.append(TableBlock(
        title="Alianzas: qué necesitamos y qué necesitan",
        columns=[Column(key="name", label="Grupo"), Column(key="we", label="Necesitamos"),
                 Column(key="they", label="Necesitan")],
        rows=[{"name": g.name, "we": g.partnership.what_we_need,
               "they": g.partnership.what_they_need} for g in partners]))

    common = {"company": COMPANY, "purpose": sh.purpose}
    docs = [
        DocumentBlock(title="Registro de stakeholders", filename="stakeholder_register.md",
                      markdown=render_template(
                          TEMPLATES, "stakeholder_register.md.j2", **common, coverage=coverage,
                          gaps=gaps, direction_labels=DIRECTION_LABELS, quadrants=quadrants,
                          chart_name=None,
                          internal=[g for g in sh.groups if g.kind == "internal"],
                          external=[g for g in sh.groups if g.kind == "external"],
                          level_labels=LEVEL_LABELS, health_labels=HEALTH_LABELS)),
        DocumentBlock(title="Mapa de stakeholders", filename="stakeholder_map.md",
                      markdown=render_template(TEMPLATES, "stakeholder_map.md.j2", **common,
                                               groups=mapped, vanity=vanity)),
        DocumentBlock(title="Evaluación del sponsor", filename="sponsor_assessment.md",
                      markdown=render_template(
                          TEMPLATES, "sponsor_assessment.md.j2", criteria=CRITERIA,
                          weights=sp.weights, assessments=assessments, recommended=recommended,
                          mismatch=mismatch, case=sp.pilot_business_case, names=names,
                          domain_names=DOMAIN_NAMES)),
        DocumentBlock(title="Plan de coalición", filename="coalition_plan.md",
                      markdown=render_template(
                          TEMPLATES, "coalition_plan.md.j2", company=COMPANY, partners=partners,
                          committee=co.committee, meetings=co.meetings, signals=signals,
                          attendance_labels=ATTENDANCE_LABELS, signal_labels=SIGNAL_LABELS,
                          forum=co.open_forum, channels=co.channels,
                          communications=co.communications)),
    ]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Stakeholders", blocks=stakeholder_blocks),
        ResultSection(title="Sponsor ejecutivo", blocks=sponsor_blocks),
        ResultSection(title="Coalición", blocks=coalition_blocks),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=2, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml")
