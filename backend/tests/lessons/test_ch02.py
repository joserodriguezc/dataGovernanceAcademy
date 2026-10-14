from datetime import date

import pytest
from pydantic import ValidationError

from academy.lessons.ch02.feedback import (
    CoalitionInput,
    delegation_counts,
    detect_signals,
)
from academy.lessons.ch02.lesson import LESSON
from academy.lessons.ch02.sponsors import (
    CRITERIA,
    Candidate,
    PilotBusinessCase,
    SponsorInput,
    assess_sponsors,
    pilot_mismatch,
    recommend,
    weighted_score,
)
from academy.lessons.ch02.stakeholders import (
    ListeningSession,
    MapEntry,
    StakeholderGroup,
    TargetResult,
    listening_gaps,
)

# --- Stakeholders ------------------------------------------------------------------------

def _group(**overrides) -> StakeholderGroup:
    base = {"id": "g", "short": "G", "name": "Grupo", "kind": "internal", "level": "executive",
            "role": "r", "health": "positive", "contributions": "c",
            "success_measures": ["m"], "influence": 3, "interest": 3}
    return StakeholderGroup(**(base | overrides))


@pytest.mark.parametrize(("influence", "interest", "quadrant"), [
    (5, 5, "Gestionar de cerca"),
    (5, 1, "Mantener satisfecho"),
    (1, 5, "Mantener informado"),
    (3, 3, "Monitorizar"),
])
def test_quadrant(influence, interest, quadrant):
    assert _group(influence=influence, interest=interest).quadrant == quadrant


def test_level_must_match_kind():
    with pytest.raises(ValidationError):
        _group(kind="external", level="executive")


def test_vanity_only_when_every_result_measures_data():
    data = TargetResult(text="95 % de completitud", type="data")
    revenue = TargetResult(text="+US$ 1 M", type="revenue")
    entry = {"objectives": ["o"], "data_solutions": ["s"], "ultimate_beneficiary": "b"}
    assert MapEntry(**entry, target_results=[data]).vanity_only
    assert not MapEntry(**entry, target_results=[data, revenue]).vanity_only


def test_listening_gaps_ignore_planned_sessions():
    sessions = [
        ListeningSession(direction=d, audience="a", format="one_on_one",
                         date=date(2026, 9, 1), done=True)
        for d in ("horizontal", "up", "down", "across")
    ] + [ListeningSession(direction="out", audience="a", format="one_on_one",
                          date=date(2026, 12, 1), done=False)]
    assert listening_gaps(sessions) == ["out"]


# --- Sponsors ----------------------------------------------------------------------------

WEIGHTS = dict.fromkeys(CRITERIA, 1.0)


def _candidate(sid: str, score: int, domain: str | None = "customer", ceo: bool = True):
    return Candidate(stakeholder=sid, domain=domain, reports_to_ceo=ceo,
                     scores=dict.fromkeys(CRITERIA, score))


def _case(domain: str = "customer") -> PilotBusinessCase:
    track = {"name": "t", "what": "w", "capabilities": ["c"], "why_it_matters": "y",
             "outcomes": ["o"], "done_to_date": "d", "milestones": ["m"], "needs": [],
             "kpis": ["k"]}
    return PilotBusinessCase(title="t", domain=domain, business_sponsor="CDAO", objective="o",
                             key_solutions=["s"], kpis=["k"], near_term_outcomes=["n"],
                             committee_asks=[], tracks=[track])


def test_weighted_score_is_normalised():
    assert weighted_score(dict.fromkeys(CRITERIA, 1), WEIGHTS) == 0
    assert weighted_score(dict.fromkeys(CRITERIA, 5), WEIGHTS) == 100
    assert weighted_score(dict.fromkeys(CRITERIA, 3), WEIGHTS) == 50


def test_cio_and_non_c_suite_are_never_recommended():
    inp = SponsorInput(weights=WEIGHTS, pilot_business_case=_case(), candidates=[
        _candidate("cio", 5, domain=None),
        _candidate("procurement", 5, domain="supplier", ceo=False),
        _candidate("cmo", 4),
        _candidate("cfo", 3, domain="sales"),
        _candidate("coo", 2, domain="store"),
    ])
    assessments = assess_sponsors(inp)
    assert [a.candidate.stakeholder for a in recommend(assessments)] == ["cmo", "cfo"]
    assert not any(a.eligible for a in assessments if a.candidate.stakeholder == "cio")


def test_pilot_mismatch_detected():
    inp = SponsorInput(weights=WEIGHTS, pilot_business_case=_case("customer"),
                       candidates=[_candidate("cfo", 5, domain="sales")])
    message = pilot_mismatch(inp.pilot_business_case, recommend(assess_sponsors(inp)))
    assert message is not None and "sales" in message
    assert pilot_mismatch(_case("sales"), recommend(assess_sponsors(inp))) is None


def test_candidate_must_score_every_criterion():
    with pytest.raises(ValidationError):
        Candidate(stakeholder="x", domain="customer", reports_to_ceo=True,
                  scores={"ceo_support": 3})


# --- Feedback del comité -----------------------------------------------------------------

def _coalition(meetings: list[dict]) -> CoalitionInput:
    return CoalitionInput.model_validate({
        "committee": {"name": "Comité", "cadence_months": 3, "members": ["A", "B"]},
        "meetings": meetings,
        "open_forum": {"name": "Foro", "cadence": "mensual", "audience": "Todos"},
        "channels": ["wiki"],
    })


def _meeting(day: int, b: str = "present", questions: int = 5, off_cycle: int = 0) -> dict:
    return {"date": date(2026, 1, day), "attendance": {"A": "present", "B": b},
            "questions": questions, "off_cycle_requests": off_cycle}


def test_repeated_delegation_is_a_membership_shift():
    co = _coalition([_meeting(1), _meeting(2, b="delegated"), _meeting(3, b="delegated")])
    assert delegation_counts(co.meetings, 3) == {"A": 0, "B": 2}
    assert [s.kind for s in detect_signals(co)] == ["membership_shift"]


def test_off_cycle_and_silence_signals():
    assert [s.kind for s in detect_signals(_coalition([_meeting(1, off_cycle=6)]))] == ["off_cycle"]
    assert [s.kind for s in detect_signals(_coalition([_meeting(1, questions=0)]))] == ["silence"]


def test_attendance_must_cover_all_members():
    bad = _meeting(1)
    bad["attendance"] = {"A": "present"}
    with pytest.raises(ValidationError):
        _coalition([bad])


# --- Extremo a extremo -------------------------------------------------------------------

def test_compute_generates_all_deliverables(compute_lesson):
    from conftest import docs
    sections = compute_lesson(LESSON)
    d = docs(sections)
    assert "Sponsor principal: Directora de Marketing (CMO)" in d["sponsor_assessment.md"]
    assert "Revisar el caso de negocio piloto" not in d["sponsor_assessment.md"]
    assert "Director Comercial delegó" in d["coalition_plan.md"]
    matrix = sections[1].blocks[0]
    assert matrix.type == "matrix" and len(matrix.points) == 21
