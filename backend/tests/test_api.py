import pytest
from fastapi.testclient import TestClient

from academy.api import create_app
from academy.catalog import Catalog, load_catalog


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path, frontend_dist=tmp_path / "no-dist"))


def test_catalog_has_17_lessons_in_4_parts():
    catalog = load_catalog()
    assert [lesson.number for lesson in catalog.lessons] == list(range(1, 18))
    assert set(catalog.parts) == {1, 2, 3, 4}


def test_catalog_rejects_forward_recommendation():
    lesson = load_catalog().lessons[0].model_dump() | {"recommended": [2]}
    with pytest.raises(ValueError, match="recomendaciones"):
        Catalog.model_validate({"parts": {1: "p"}, "lessons": [lesson]})


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_lesson_navigation(client):
    first = client.get("/api/lessons/1").json()
    assert first["previous"] is None and first["next"] == 2
    assert client.get("/api/lessons/17").json()["next"] is None
    assert client.get("/api/lessons/99").status_code == 404


def test_progress_and_recommendations(client):
    eight = client.get("/api/lessons/8").json()["state"]
    assert eight["missing_recommended"] == [6, 7]
    client.put("/api/progress/6", json={"completed": True})
    states = client.put("/api/progress/7", json={"completed": True}).json()
    assert states[7]["missing_recommended"] == []
    assert states[5]["completed"] and states[5]["completed_at"]
    states = client.put("/api/progress/7", json={"completed": False}).json()
    assert states[7]["missing_recommended"] == [7]
    states = client.delete("/api/progress").json()
    assert not any(s["completed"] for s in states)


def test_progress_persists_between_apps(tmp_path):
    no_dist = tmp_path / "no-dist"
    TestClient(create_app(data_dir=tmp_path, frontend_dist=no_dist)).put(
        "/api/progress/1", json={"completed": True})
    states = TestClient(create_app(data_dir=tmp_path, frontend_dist=no_dist)).get(
        "/api/lessons").json()["states"]
    assert states[0]["completed"]
