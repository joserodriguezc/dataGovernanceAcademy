"""Lección 10: gestión de datos primarios (golden record de cliente).

Misma lógica que chapters/ch10_datos_primarios_mdm/run.py del laboratorio. Escribe en el
warehouse el esquema pdm (hub de datos primarios) y curated.dim_customer.
"""

import re
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from academy.blocks import (
    BarItem,
    BarListBlock,
    CalloutBlock,
    Column,
    DocumentBlock,
    Kpi,
    KpisBlock,
    ResultSection,
    TableBlock,
)
from academy.core.reporting import fmt_money, fmt_num, fmt_pct, render_template
from academy.core.synthetic.io import read_truth
from academy.core.warehouse import connect
from academy.lessons.base import InputSpec, LessonContext, LessonDef

from .config import PdmConfig, ReferenceData
from .matching import cluster, evaluate, find_pairs
from .parties import load_parties
from .publish import publish
from .reference import enrich, hierarchy_counts, reference_table
from .survivorship import golden_records

LESSON_DIR = Path(__file__).parent
INPUTS = LESSON_DIR / "inputs"
TEMPLATES = LESSON_DIR / "templates"
COMPANY = "NovaMercado"
CHECKS = {"Email válido": "email", "Teléfono válido": "phone",
          "Código postal válido": "postal_code"}

INPUT_SPECS = [
    InputSpec("pdm", "Datos primarios",
              "Sistemas de origen, reglas de emparejamiento, reglas de supervivencia por "
              "atributo y supuestos de valor.", PdmConfig, INPUTS / "pdm.yaml"),
    InputSpec("reference", "Datos de referencia",
              "Provincias, comunidades y regiones de venta para enriquecer al cliente.",
              ReferenceData, INPUTS / "reference_data.yaml"),
]


def _valid_share(series: pd.Series, pattern: str | None) -> float:
    if pattern is None:
        return float(series.notna().mean())
    regex = re.compile(pattern)
    return float(series.map(lambda v: isinstance(v, str) and bool(regex.fullmatch(v))).mean())


def compute(inputs: dict[str, BaseModel], ctx: LessonContext) -> list[ResultSection]:
    cfg: PdmConfig = inputs["pdm"]
    ref: ReferenceData = inputs["reference"]
    links, _ = read_truth(ctx.raw_dir)
    person = links.set_index("source_id")["person_id"]

    with connect(ctx.db_path) as con:
        parties = load_parties(con, cfg)
        auto, review = find_pairs(parties, cfg.matching)
        roots = cluster(len(parties), auto)
        ids = {r: f"NM-C{i + 1:06d}" for i, r in enumerate(sorted(set(roots)))}
        parties["group"] = [ids[r] for r in roots]
        golden, attribution = golden_records(parties, cfg)
        golden = enrich(golden.rename(columns={"group": "golden_id"}), ref)
        truth = parties["source_id"].map(person)
        review_rows = pd.DataFrame([{
            "record_a": f"{parties.at[p.a, 'source']} {parties.at[p.a, 'source_id']}",
            "record_b": f"{parties.at[p.b, 'source']} {parties.at[p.b, 'source_id']}",
            "name_a": parties.at[p.a, "name_key"], "name_b": parties.at[p.b, "name_key"],
            "rule": p.rule, "score": round(p.score, 1), "status": "pendiente",
        } for p in review], columns=["record_a", "record_b", "name_a", "name_b", "rule",
                                     "score", "status"])
        xref = parties[["source", "source_id", "group"]].rename(columns={"group": "golden_id"})
        publish(con, golden, xref, attribution, reference_table(ref), review_rows,
                pd.Timestamp("2026-10-12").date())
        total_sales, identified_sales, omnichannel, buyers = con.execute("""
            SELECT (SELECT sum(amount) FROM staging.stg_pos_sales)
                 + (SELECT sum(amount) FROM staging.stg_ecom_orders
                    WHERE status NOT IN ('cancelado', 'devuelto')),
                   (SELECT sum(net_sales) FROM curated.dim_customer),
                   (SELECT count(*) FROM curated.dim_customer WHERE channels_purchased = 2),
                   (SELECT count(*) FROM curated.dim_customer WHERE channels_purchased > 0)
            """).fetchone()

    score = evaluate(parties["group"], truth)
    confirmed = [p for p in review if truth[p.a] == truth[p.b]]
    score_reviewed = evaluate(pd.Series([ids[r] for r in cluster(len(parties),
                                                                 auto + confirmed)]), truth)
    per_source = [(cfg.sources[s].label, int((parties["source"] == s).sum()))
                  for s in cfg.sources]
    completeness = [(name, _valid_share(parties[col], cfg.attributes[col].validate_),
                     _valid_share(golden[col], cfg.attributes[col].validate_))
                    for name, col in CHECKS.items()]
    postal_re = re.compile(cfg.attributes["postal_code"].validate_)
    bad_postal_groups = set(parties.loc[parties["postal_code"].map(
        lambda v: isinstance(v, str) and not postal_re.fullmatch(v)), "group"])
    postal_fixed = int(golden[golden["golden_id"].isin(bad_postal_groups)]["province"]
                       .notna().sum())
    labels = {s: c.label for s, c in cfg.sources.items()}
    attr_summary = {}
    for attr, part in attribution.groupby("attribute"):
        shares = part["source"].value_counts(normalize=True)
        attr_summary[attr] = " · ".join(f"{labels.get(s, s)} {fmt_pct(v, 1)}"
                                        for s, v in shares.items())
    hier = hierarchy_counts(golden)
    regions = [(region, int(g["customers"].sum()),
                ", ".join(f"{r.community} ({r.customers})" for r in g.itertuples()))
               for region, g in hier.groupby("sales_region")]
    emailable = parties[parties["source"].isin(cfg.attributes["email"].sources)]
    dup_contacts = int(emailable["email"].notna().sum() - golden["email"].notna().sum())
    value = cfg.value
    campaign_saving = dup_contacts * value.campaigns_per_year * value.cost_per_contact
    hours_saving = value.hours_manual_dedup * value.automation_share * value.cost_per_hour
    review_view = [{"a_label": r.record_a, "b_label": r.record_b, "rule": r.rule,
                    "score": r.score, "same": truth[p.a] == truth[p.b]}
                   for r, p in zip(review_rows.itertuples(), review, strict=True)]
    identified_share = identified_sales / total_sales if total_sales else 0.0

    summary: list = [KpisBlock(items=[
        Kpi(label="Clientes únicos", value=fmt_num(len(golden)),
            detail=f"A partir de {fmt_num(len(parties))} registros de {len(per_source)} "
                   "sistemas"),
        Kpi(label="Precisión del emparejamiento", value=fmt_pct(score.precision, 1),
            detail="Parejas unidas que son de verdad la misma persona",
            tone="good" if score.precision >= 0.99 else "warning"),
        Kpi(label="Recall del emparejamiento", value=fmt_pct(score.recall, 1),
            detail=f"{fmt_pct(score_reviewed.recall, 1)} tras la revisión del steward"),
        Kpi(label="Valor estimado al año", value=fmt_money(campaign_saving + hours_saving),
            detail="Campañas sin duplicados y menos deduplicación manual"),
    ]), CalloutBlock(
        tone="info", title="Lo que deja en el warehouse",
        text="El hub de datos primarios (esquema pdm) y curated.dim_customer. Vuelve a "
             "ejecutar las lecciones 4 y 5: los duplicados de cliente se miden ahora sobre el "
             "registro único.")]

    total = sum(n for _, n in per_source)
    dedup = [
        BarListBlock(
            title="Deduplicación de clientes",
            subtitle="Registros de cada sistema frente a clientes únicos tras el hub",
            min_value=0, max_value=total,
            items=[*[BarItem(label=label, value=n, display=fmt_num(n)) for label, n in per_source],
                   BarItem(label="Total de registros", value=total, display=fmt_num(total)),
                   BarItem(label="Clientes únicos", value=len(golden),
                           display=fmt_num(len(golden)), ok=True)],
            legend="Número de registros"),
        TableBlock(
            title="Calidad antes y después del registro único",
            columns=[Column(key="check", label="Comprobación"),
                     Column(key="before", label="En los sistemas", align="right"),
                     Column(key="after", label="En el registro único", align="right")],
            rows=[{"check": n, "before": fmt_pct(b, 1), "after": fmt_pct(a, 1)}
                  for n, b, a in completeness]),
        TableBlock(
            title="De qué sistema sale cada atributo (supervivencia)",
            columns=[Column(key="attr", label="Atributo"), Column(key="src", label="Origen")],
            rows=[{"attr": a, "src": s} for a, s in attr_summary.items()]),
    ]

    review_blocks: list = [TableBlock(
        title="Cola de revisión del steward",
        description="Parejas dudosas que no se unen solas. Como los datos son sintéticos, se "
                    "sabe cuáles son de verdad la misma persona.",
        columns=[Column(key="a", label="Registro A"), Column(key="b", label="Registro B"),
                 Column(key="rule", label="Regla"),
                 Column(key="score", label="Similitud", align="right"),
                 Column(key="same", label="¿Misma persona?")],
        rows=[{"a": r["a_label"], "b": r["b_label"], "rule": r["rule"],
               "score": fmt_num(r["score"], 1), "same": "✅ Sí" if r["same"] else "❌ No"}
              for r in review_view])]

    business = [KpisBlock(items=[
        Kpi(label="Clientes que compran en tienda y online", value=fmt_num(omnichannel),
            detail=f"de {fmt_num(buyers)} que compran"),
        Kpi(label="Ventas atribuidas a un cliente", value=fmt_money(identified_sales),
            detail=f"{fmt_pct(identified_share)} del total"),
        Kpi(label="Contactos duplicados eliminados", value=fmt_num(dup_contacts),
            detail=f"{fmt_money(campaign_saving)} al año en campañas"),
        Kpi(label="Códigos postales corregidos", value=fmt_num(postal_fixed),
            detail="Gracias a otro sistema del mismo cliente"),
    ]), TableBlock(
        title="Jerarquía geográfica (datos de referencia)",
        columns=[Column(key="region", label="Región de ventas"),
                 Column(key="n", label="Clientes", align="right"),
                 Column(key="communities", label="Comunidades")],
        rows=[{"region": r, "n": fmt_num(n), "communities": c} for r, n, c in regions])]

    docs = [DocumentBlock(title="Datos primarios de cliente", filename="primary_data.md",
                          markdown=render_template(
                              TEMPLATES, "primary_data.md.j2", company=COMPANY, cfg=cfg,
                              ref=ref, records=len(parties), golden_count=len(golden),
                              per_source=per_source, chart_name=None,
                              rules=pd.Series([p.rule for p in auto]).value_counts().items(),
                              review=review_view, score=score, score_reviewed=score_reviewed,
                              source_labels=labels, attribution=attr_summary,
                              completeness=completeness, postal_fixed=postal_fixed,
                              regions=regions, invalid_postal=int(golden["province"].isna().sum()),
                              multi_system=int((golden["source_records"] > 1).sum()),
                              omnichannel=omnichannel, buyers=buyers,
                              identified_sales=identified_sales,
                              identified_share=identified_share,
                              consented=int(golden["consent_marketing"].fillna(False)
                                            .astype(bool).sum()),
                              dup_contacts=dup_contacts, campaign_saving=campaign_saving,
                              hours_saving=hours_saving))]

    return [
        ResultSection(title="Resumen", blocks=summary),
        ResultSection(title="Registro único", blocks=dedup),
        ResultSection(title="Revisión del steward", blocks=review_blocks),
        ResultSection(title="Valor para el negocio", blocks=business),
        ResultSection(title="Documentos", blocks=docs),
    ]


LESSON = LessonDef(number=10, inputs=INPUT_SPECS, compute=compute,
                   content_file=LESSON_DIR / "content.yaml", requires_warehouse=True)
