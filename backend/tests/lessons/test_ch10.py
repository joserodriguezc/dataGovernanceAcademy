from datetime import date

import pandas as pd
import pytest

from academy.core.config import load_yaml
from academy.core.warehouse import connect
from academy.lessons.ch04.evidence import indicators
from academy.lessons.ch09.review import make_linter
from academy.lessons.ch10.config import Matching, PdmConfig, ReferenceData
from academy.lessons.ch10.lesson import INPUTS, LESSON
from academy.lessons.ch10.matching import cluster, evaluate, find_pairs
from academy.lessons.ch10.parties import name_key
from academy.lessons.ch10.publish import age_band
from academy.lessons.ch10.reference import enrich
from academy.lessons.ch10.survivorship import golden_records

CFG = PdmConfig.model_validate(load_yaml(INPUTS / "pdm.yaml"))
REF = ReferenceData.model_validate(load_yaml(INPUTS / "reference_data.yaml"))
M = Matching(auto_match_score=90, review_score=75)


def _parties(rows: list[dict]) -> pd.DataFrame:
    base = {c: None for c in ("email", "phone", "postal_code", "birth_date", "loyalty_tier",
                              "consent_marketing", "created_at", "first_name", "last_name")}
    df = pd.DataFrame([base | r for r in rows])
    df["name_key"] = df["name"].map(name_key)
    return df.drop(columns="name")


def test_name_key_ignores_accents_case_and_spaces():
    assert name_key("  JOSÉ  Núñez ") == "jose nunez"


def test_matching_rules():
    df = _parties([
        dict(source="crm", source_id="c1", name="Ana Ruiz Gil", email="a@x.es", phone="611111111",
             postal_code="28013"),
        dict(source="ecom", source_id="e1", name="Ana Ruiz Gil", email="a@x.es",
             postal_code="2801"),                                      # email idéntico
        dict(source="pos", source_id="p1", name="ANA RUIZ", postal_code="28013"),  # CP + nombre
        dict(source="pos", source_id="p2", name="ANA RUIZ", postal_code="41001"),  # ¿mudanza?
        dict(source="crm", source_id="c2", name="Luis Pérez", phone="622222222",
             postal_code="08001"),
    ])
    auto, review = find_pairs(df, M)
    groups = cluster(len(df), auto)
    assert groups[0] == groups[1] == groups[2]
    assert len({groups[0], groups[3], groups[4]}) == 3
    assert {(p.a, p.b) for p in review} == {(0, 3), (1, 3), (2, 3)}
    assert all(p.rule == "mismo nombre, distinto CP" for p in review)


def test_pairwise_evaluation():
    score = evaluate(pd.Series(["g1", "g1", "g1", "g2"]), pd.Series(["p1", "p1", "p2", "p2"]))
    assert (score.true_pairs, score.predicted_pairs, score.correct_pairs) == (2, 3, 1)
    assert score.precision == pytest.approx(1 / 3) and score.recall == 0.5


def test_survivorship_trust_order_validation_and_recency():
    df = _parties([
        dict(source="crm", source_id="c-old", name="x", first_name="Ana", email="viejo@x.es",
             postal_code="28013", created_at=pd.Timestamp("2020-01-01")),
        dict(source="crm", source_id="c-new", name="x", first_name="Ana", email="nuevo@x.es",
             postal_code="2801", created_at=pd.Timestamp("2025-01-01")),   # CP inválido
        dict(source="pos", source_id="p1", name="x", first_name="ANA", phone="633333333",
             postal_code="28014"),
    ])
    df["group"] = "G1"
    golden, attribution = golden_records(df, CFG)
    g = golden.iloc[0]
    assert g.email == "nuevo@x.es"                 # mismo sistema: gana el más reciente
    assert g.postal_code == "28013"                # el más reciente no es válido: siguiente
    assert g.phone == "633333333"                  # el CRM no lo tiene: pasa a tiendas
    assert not g.consent_marketing                 # sin registro, no hay consentimiento
    src = attribution.set_index("attribute")["source_id"]
    assert (src["email"], src["phone"]) == ("c-new", "p1")


def test_enrichment_and_hierarchies():
    out = enrich(pd.DataFrame({"postal_code": ["28013", "41001", "99999", None]}), REF)
    assert out["province"].tolist()[:2] == ["Madrid", "Sevilla"]
    assert out["sales_region"].tolist()[:2] == ["Centro", "Sur"]
    assert out["province"].isna().tolist()[2:] == [True, True]


@pytest.mark.parametrize(("birth", "band"), [(date(2000, 10, 13), "25-34"),
                                             (date(2000, 10, 12), "25-34"),
                                             (date(2002, 10, 13), "18-24"), (None, None)])
def test_age_band(birth, band):
    assert age_band(birth, date(2026, 10, 12)) == band


def test_reference_data_requires_every_community_in_one_region():
    data = load_yaml(INPUTS / "reference_data.yaml")
    data["sales_regions"]["Centro"].remove("Comunidad de Madrid")
    with pytest.raises(ValueError):
        ReferenceData.model_validate(data)


def test_compute_builds_golden_record(compute_lesson, workspace_copy):
    db = workspace_copy.db_path
    sections = compute_lesson(LESSON, workspace=workspace_copy)
    kpis = {k.label: k.value for k in sections[0].blocks[0].items}
    assert kpis["Precisión del emparejamiento"] == "100,0 %"
    with connect(db, read_only=True) as con:
        assert indicators(con)["crm_duplicate_phones"] == 0.0
        columns = [r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = "
            "'curated' AND table_name = 'dim_customer'").fetchall()]
        xref, golden = con.execute("SELECT (SELECT count(*) FROM pdm.customer_xref), "
                                   "(SELECT count(*) FROM pdm.customer_golden)").fetchone()
    assert xref > golden > 0
    linter = make_linter()
    assert not [c for c in columns if linter.pii_category(c)]  # sin PII directa en curated
