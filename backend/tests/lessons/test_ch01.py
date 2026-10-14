from datetime import date

import pytest
from pydantic import ValidationError

from academy.lessons.ch01.business_case import (
    TimelineOption,
    evaluate_option,
    monthly_flows,
    npv,
    payback_month,
)
from academy.lessons.ch01.charter import (
    LaunchInput,
    ProgramMission,
    Signal,
    assess_launch,
    lint_vision,
)
from academy.lessons.ch01.equity import DataEquityInput, evaluate_equity
from academy.lessons.ch01.lesson import LESSON
from academy.lessons.ch01.policy import POLICY_SECTIONS
from academy.lessons.ch01.scorecard import (
    DomainStatus,
    ScorecardInput,
    SystemStatus,
    corporate_scorecard,
    rag_status,
)

# --- Data equity -------------------------------------------------------------------------

EQUITY = {
    "hourly_rate_usd": 50,
    "assets": [
        {"id": "A1", "name": "a", "domain": "customer", "description": "", "vetted_by": "CMO",
         "current": {"revenue_usd": 100}, "target": {"revenue_usd": 300, "hours_saved": 2}},
        {"id": "A2", "name": "b", "domain": "product", "description": "", "vetted_by": None,
         "current": {}, "target": {"revenue_usd": 1000}},
    ],
    "liabilities": [
        {"id": "L1", "name": "c", "domain": "sales", "description": "", "vetted_by": "CFO",
         "current": {"fine_probability": 0.5, "fine_amount_usd": 1000, "hours_lost": 4},
         "target": {"fine_probability": 0.1, "fine_amount_usd": 1000}},
    ],
}


def test_equity_is_assets_minus_liabilities():
    s = evaluate_equity(DataEquityInput.model_validate(EQUITY))
    assert s.assets("current") == 100
    assert s.liabilities("current") == 500 + 4 * 50
    assert s.equity("current") == 100 - 700
    assert s.equity("target") == (300 + 100 + 1000) - 100


def test_benefit_counts_only_vetted_lines_when_conservative():
    s = evaluate_equity(DataEquityInput.model_validate(EQUITY))
    # A1: +300 ; L1: 700 -> 100 = +600 ; A2 sin validar: +1000
    assert s.annual_benefit(vetted_only=True) == 900
    assert s.annual_benefit() == 1900
    assert [ln.id for ln in s.unvetted] == ["A2"]


def test_unknown_domain_is_rejected():
    bad = {**EQUITY, "assets": [{**EQUITY["assets"][0], "domain": "marketing"}]}
    with pytest.raises(ValidationError):
        DataEquityInput.model_validate(bad)


# --- Caso de negocio ---------------------------------------------------------------------

OPTION = TimelineOption(id="x", name="X", description="", duration_months=4,
                        build_cost_usd=400, run_cost_annual_usd=120)


def test_monthly_flows_spread_build_and_ramp_benefit():
    costs, benefits = monthly_flows(OPTION, annual_benefit=1200, horizon_months=6)
    assert costs == [100, 100, 100, 100, 10, 10]
    assert benefits == [25, 50, 75, 100, 100, 100]


def test_npv_with_zero_rate_is_plain_sum():
    assert npv([-100, 50, 80], 0.0) == pytest.approx(30)


def test_npv_discounts_future_flows():
    assert npv([0] * 11 + [110], 0.10) == pytest.approx(100)


def test_payback_month():
    assert payback_month([-10, -5, 0, 4]) == 3
    assert payback_month([-10, -5]) is None


def test_evaluate_option_totals_and_roi():
    r = evaluate_option(OPTION, annual_benefit=1200, horizon_months=6, annual_rate=0)
    assert r.total_cost == 420
    assert r.total_benefit == 450
    assert r.roi == pytest.approx(30 / 420)
    assert r.payback_month == 6


# --- Charter ---------------------------------------------------------------------------

def test_vision_lint_flags_jargon_and_length():
    assert lint_vision("Decidimos con datos fiables y clientes felices.") == []
    issues = lint_vision("Un data lake con linaje y metadatos para todos.")
    assert len(issues) == 3
    assert lint_vision("palabra " * 41)[0].startswith("Tiene 41 palabras")


def test_program_mission_statement():
    m = ProgramMission(what="capacidades", for_whom="todos", how=["A", "B", "C"])
    assert m.statement == "Desarrollamos capacidades para todos, A, B y C."


def _launch(drivers: bool, warning: bool) -> LaunchInput:
    return LaunchInput(drivers=[Signal(id="d", name="Regulatorio", present=drivers)],
                       warning_signs=[Signal(id="w", name="Fusión", present=warning)])


@pytest.mark.parametrize(("drivers", "warning", "verdict"), [
    (True, False, "lanzar"),
    (True, True, "esperar"),
    (False, False, "esperar"),
])
def test_launch_decision(drivers, warning, verdict):
    assert assess_launch(_launch(drivers, warning)).verdict == verdict


# --- Scorecard -------------------------------------------------------------------------

AS_OF = date(2026, 10, 12)


@pytest.mark.parametrize(("pct", "due", "status"), [
    (1.0, date(2026, 1, 1), "green"),     # completa, aunque haya vencido
    (0.5, date(2026, 10, 1), "red"),      # vencida
    (0.5, date(2026, 10, 30), "yellow"),  # vence en 18 días
    (0.5, date(2027, 1, 1), "green"),     # todavía en plazo
])
def test_rag_status(pct, due, status):
    assert rag_status(pct, due, AS_OF, at_risk_days=30) == status


def test_corporate_scorecard_counts_domains():
    due = dict.fromkeys(
        ["domain_executive", "data_stewards", "systems_identified", "system_owners", "cdes",
         "dq_rules", "business_glossary", "data_dictionary", "reference_data"],
        date(2027, 1, 1),
    )
    sc = ScorecardInput(as_of=AS_OF, due_dates=due, domains=[
        DomainStatus(id="customer", executive="CMO", stewards=["s"],
                     systems=[SystemStatus(name="crm", owner="o", cdes=True),
                              SystemStatus(name="pos", owner=None, cdes=True)]),
        DomainStatus(id="supplier"),
    ])
    metrics = {m.key: m for m in corporate_scorecard(sc)}
    executive = metrics["domain_executive"]
    assert (executive.numerator, executive.denominator) == (1, 2)
    assert metrics["system_owners"].numerator == 0  # al POS le falta owner
    assert metrics["cdes"].numerator == 1  # todos los sistemas de cliente tienen CDE


def test_scorecard_requires_due_date_for_every_metric():
    with pytest.raises(ValidationError):
        ScorecardInput(as_of=AS_OF, due_dates={}, domains=[DomainStatus(id="customer")])


# --- Extremo a extremo -------------------------------------------------------------------

def _default_inputs():
    return {spec.id: spec.model.model_validate(spec.default()) for spec in LESSON.inputs}


def _docs(sections):
    return {b.filename: b.markdown for s in sections for b in s.blocks if b.type == "document"}


def test_compute_generates_all_deliverables():
    sections = LESSON.compute(_default_inputs())
    assert [s.title for s in sections] == ["Resumen", "Caso de negocio", "Data equity",
                                           "EDG Scorecard", "Documentos"]
    docs = _docs(sections)
    for number, section in enumerate(POLICY_SECTIONS, start=1):
        assert f"## {number}. {section}" in docs["data_governance_policy.md"]
    assert "Decisión: LANZAR" in docs["charter.md"]
    assert "La visión es breve y no usa jerga de datos" in docs["charter.md"]
    assert "![" not in docs["business_case.md"]  # el gráfico se dibuja en la app


def test_compute_matches_lab_numbers():
    kpis = LESSON.compute(_default_inputs())[0].blocks[0].items
    values = {k.label.split(" (")[0]: k.value for k in kpis}
    assert values["Data equity hoy"] == "-US$ 1.077.500"
    assert values["Beneficio anual en el caso"] == "US$ 2.582.500"
    assert values["VAN de la opción recomendada"] == "US$ 2.250.458"


def test_unvetted_benefits_raise_npv():
    inputs = _default_inputs()
    base = LESSON.compute(inputs)[0].blocks[0].items[2].value
    inputs["business_case"] = inputs["business_case"].model_copy(
        update={"include_unvetted_benefits": True})
    assert LESSON.compute(inputs)[0].blocks[0].items[2].value != base
