"""API de Data Governance Academy."""

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from academy import __version__
from academy.catalog import Catalog, Lesson, load_catalog
from academy.paths import DATA_DIR, FRONTEND_DIST
from academy.progress import LessonState, ProgressStore, lesson_states


class CatalogOut(BaseModel):
    parts: dict[int, str]
    lessons: list[Lesson]
    states: list[LessonState]


class LessonOut(BaseModel):
    lesson: Lesson
    state: LessonState
    previous: int | None
    next: int | None


class CompletedIn(BaseModel):
    completed: bool


def create_app(data_dir: Path = DATA_DIR, catalog: Catalog | None = None,
               frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    catalog = catalog or load_catalog()
    store = ProgressStore(data_dir / "progress.json")
    api = APIRouter(prefix="/api")

    def _lesson_or_404(number: int) -> Lesson:
        lesson = catalog.get(number)
        if lesson is None:
            raise HTTPException(404, f"No existe la lección {number}")
        return lesson

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @api.get("/lessons")
    def lessons() -> CatalogOut:
        return CatalogOut(parts=catalog.parts, lessons=catalog.lessons,
                          states=lesson_states(catalog, store.load()))

    @api.get("/lessons/{number}")
    def lesson(number: int) -> LessonOut:
        current = _lesson_or_404(number)
        states = {s.number: s for s in lesson_states(catalog, store.load())}
        numbers = [x.number for x in catalog.lessons]
        i = numbers.index(number)
        return LessonOut(lesson=current, state=states[number],
                         previous=numbers[i - 1] if i > 0 else None,
                         next=numbers[i + 1] if i + 1 < len(numbers) else None)

    @api.put("/progress/{number}")
    def set_progress(number: int, body: CompletedIn) -> list[LessonState]:
        _lesson_or_404(number)
        return lesson_states(catalog, store.set_completed(number, body.completed))

    @api.delete("/progress")
    def reset_progress() -> list[LessonState]:
        store.reset()
        return lesson_states(catalog, store.load())

    app = FastAPI(title="Data Governance Academy", version=__version__)
    app.include_router(api)

    # En producción local, FastAPI sirve el frontend ya compilado (npm run build).
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            file = frontend_dist / path
            return FileResponse(file if path and file.is_file() else frontend_dist / "index.html")

    return app


app = create_app()
