from datetime import date

import pytest
from pydantic import ValidationError

from academy.lessons.ch03.lesson import LESSON
from academy.lessons.ch03.org_model import OrgFacts, recommend_model
from academy.lessons.ch03.raci import Activity, RaciInput, idle_roles
from academy.lessons.ch03.rhythm import (
    Every,
    Forum,
    ForumsInput,
    add_months,
    meeting_dates,
)
from academy.lessons.ch03.team import (
    FunctionalRoles,
    Member,
    Role,
    Skills,
    hiring_order_issues,
    org_chart_mermaid,
    skill_gaps,
)

# --- Modelo organizativo -----------------------------------------------------------------

def _facts(**overrides) -> OrgFacts:
    base = dict(has_data_capabilities=True, capabilities_consistent=True,
                major_trust_issues=False, broad_support=True, strong_bu_leaders=True,
                central_office_strong=True)
    return OrgFacts(**(base | overrides))


def test_no_capabilities_starts_with_small_federated_office():
    rec = recommend_model(_facts(has_data_capabilities=False))
    assert (rec.model, rec.target) == ("federated", "hub_and_spoke")


def test_inconsistency_and_trust_issues_centralize_temporarily():
    rec = recommend_model(_facts(capabilities_consistent=False, major_trust_issues=True))
    assert (rec.model, rec.target, rec.horizon) == ("centralized", "hub_and_spoke", "12-24 meses")


def test_hub_and_spoke_requires_a_strong_central_office():
    assert recommend_model(_facts()).prerequisites == []
    weak = recommend_model(_facts(central_office_strong=False))
    assert weak.model == "hub_and_spoke" and weak.prerequisites


# --- Equipo ------------------------------------------------------------------------------

def _role(rid: str, start: date, priority: int | None = None, status: str = "planned",
          reports_to: str | None = "cdao") -> Role:
    return Role(id=rid, title=rid, function="governance_strategy", reports_to=reports_to,
                status=status, start=start, headcount=1, annual_cost_usd=100,
                book_priority=priority)


def test_hiring_order_warns_when_later_leader_starts_first():
    roles = [_role("dg", date(2027, 5, 1), 1), _role("sol", date(2027, 2, 1), 2)]
    assert len(hiring_order_issues(roles)) == 1
    assert hiring_order_issues([_role("dg", date(2027, 1, 1), 1),
                                _role("sol", date(2027, 2, 1), 2)]) == []


def test_filled_roles_do_not_count_for_hiring_order():
    roles = [_role("dg", date(2027, 5, 1), 1),
             _role("de", date(2025, 1, 1), 4, status="filled")]
    assert hiring_order_issues(roles) == []


def test_org_chart_marks_pending_roles():
    chart = org_chart_mermaid([_role("cdao", date(2026, 1, 1), status="filled", reports_to=None),
                               _role("dg", date(2027, 1, 1))])
    assert "cdao --> dg" in chart and "class dg pending" in chart


def test_functional_role_gaps():
    f = FunctionalRoles(domain="supplier", executive=None, business_stewards=[],
                        technical_stewards=["t"])
    assert f.gaps == ["ejecutivo de dominio", "steward de negocio"]


def test_skill_gap_actions():
    skills = Skills(required={"A": 3, "B": 3, "C": 3, "D": 2}, members=[
        Member(name="x", role="r", levels={"A": 3, "B": 2, "C": 1, "D": 2}),
        Member(name="y", role="r", levels={"A": 3, "B": 0, "C": 0, "D": 1}),
    ])
    actions = {g.skill: g.action for g in skill_gaps(skills)}
    assert actions == {"A": "Cubierta", "B": "Formar (upskilling)",
                       "C": "Contratar o incorporar experiencia externa",
                       "D": "Formar a una segunda persona"}


# --- RACI --------------------------------------------------------------------------------

ROLES = {"a": "A", "b": "B", "c": "C"}


def test_raci_letters_and_idle_roles():
    act = Activity(name="x", A="a", R=["a"], C=["b"])
    assert (act.letters("a"), act.letters("b"), act.letters("c")) == ("A/R", "C", "")
    assert idle_roles(RaciInput(roles=ROLES, activities=[act])) == ["B", "C"]


def test_raci_rejects_unknown_roles_and_conflicting_letters():
    with pytest.raises(ValidationError):
        RaciInput(roles=ROLES, activities=[Activity(name="x", A="z", R=["a"])])
    with pytest.raises(ValidationError):
        RaciInput(roles=ROLES, activities=[Activity(name="x", A="a", R=["b"], I=["b"])])


# --- Ritmo -------------------------------------------------------------------------------

def _forum(fid: str, reports_to: str | None, every: dict) -> Forum:
    return Forum(id=fid, name=fid, purpose="p", importance="i", chair="c",
                 member_level="c_suite", members=["m"], responsibilities=["r"],
                 reports_to=reports_to, first_meeting=date(2027, 1, 31),
                 every=Every(**every), communication=[], evaluation="e")


def test_add_months_clamps_to_month_end():
    assert add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert add_months(date(2027, 11, 15), 3) == date(2028, 2, 15)


def test_meeting_dates_quarterly_and_biweekly():
    quarterly = meeting_dates(_forum("q", None, {"months": 3}), date(2027, 1, 1), date(2028, 1, 1))
    assert [d.month for d in quarterly] == [1, 4, 7, 10]
    biweekly = meeting_dates(_forum("b", None, {"weeks": 2}), date(2027, 1, 1), date(2027, 3, 1))
    assert [d.day for d in biweekly] == [31, 14, 28]  # 31/01, 14/02 y 28/02


def test_every_needs_exactly_one_unit():
    with pytest.raises(ValidationError):
        Every(weeks=2, months=1)


def test_forum_hierarchy_rejects_cycles():
    with pytest.raises(ValidationError):
        ForumsInput(calendar={"start": date(2027, 1, 1), "months": 12}, portfolio=[],
                    forums=[_forum("a", "b", {"months": 1}), _forum("b", "a", {"months": 1})])


# --- Extremo a extremo -------------------------------------------------------------------

def test_compute_generates_all_deliverables(compute_lesson):
    from conftest import docs
    sections = compute_lesson(LESSON)
    d = docs(sections)
    assert "Modelo recomendado: Centralizado" in d["org_model.md"]
    assert sections[2].blocks[0].columns[1].label == "CDAO"


def test_budget_comes_from_the_learners_lesson_1(compute_lesson):
    """Si el alumno recomienda la opción lenta en la lección 1, el equipo ya no cabe."""
    from academy.lessons.ch01.lesson import INPUT_SPECS

    def stored(lesson, spec):
        data = spec.default()
        if lesson == 1 and spec.id == "business_case":
            data["recommended_option"] = "slow"
        return data

    base = compute_lesson(LESSON)[0].blocks[0].items[1]
    slow = compute_lesson(LESSON, stored)[0].blocks[0].items[1]
    assert base.tone == "good" and slow.tone == "bad"
    assert INPUT_SPECS[2].id == "business_case"
