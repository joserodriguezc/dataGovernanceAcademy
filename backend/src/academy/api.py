"""API de Data Governance Academy."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from academy import __version__
from academy.blocks import LessonResult
from academy.catalog import Catalog, Lesson, load_catalog
from academy.lessons.base import InputSpec, LessonContent, LessonContext, LessonDef
from academy.lessons.registry import LESSONS
from academy.paths import DATA_DIR, FRONTEND_DIST
from academy.progress import LessonState, ProgressStore, lesson_states
from academy.schema import form_schema
from academy.state import LessonStore
from academy.workspace import LABELS as WORKSPACE_LABELS
from academy.workspace import Workspace, WorkspaceSettings, WorkspaceStatus


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


class InputOut(BaseModel):
    id: str
    title: str
    description: str
    json_schema: dict[str, Any]
    data: dict[str, Any]
    custom: bool  # el alumno lo ha editado (si no, son los valores por defecto)


class InputIn(BaseModel):
    data: dict[str, Any]


class WorkspaceOut(BaseModel):
    status: WorkspaceStatus
    json_schema: dict[str, Any]


def _validation_detail(exc: ValidationError) -> list[dict[str, str]]:
    return [{"loc": ".".join(str(x) for x in e["loc"]), "msg": e["msg"]} for e in exc.errors()]


def create_app(data_dir: Path = DATA_DIR, catalog: Catalog | None = None,
               frontend_dist: Path = FRONTEND_DIST,
               registry: dict[int, LessonDef] | None = None) -> FastAPI:
    registry = LESSONS if registry is None else registry
    base = catalog or load_catalog()
    catalog = base.model_copy(update={"lessons": [
        x.model_copy(update={
            "status": "available" if x.number in registry else "planned",
            "requires_warehouse": x.number in registry and registry[x.number].requires_warehouse,
        }) for x in base.lessons]})
    store = ProgressStore(data_dir / "progress.json")
    lessons_store = LessonStore(data_dir)
    workspace = Workspace(data_dir)
    api = APIRouter(prefix="/api")

    def _def_or_404(number: int) -> LessonDef:
        if number not in registry:
            raise HTTPException(404, f"La lección {number} todavía no es interactiva")
        return registry[number]

    def _spec_or_404(lesson: LessonDef, input_id: str) -> InputSpec:
        spec = lesson.input_spec(input_id)
        if spec is None:
            raise HTTPException(404, f"La lección {lesson.number} no tiene la entrada {input_id}")
        return spec

    def _input_out(lesson: LessonDef, spec: InputSpec) -> InputOut:
        return InputOut(id=spec.id, title=spec.title, description=spec.description,
                        json_schema=form_schema(spec.model, lesson.content().labels),
                        data=lessons_store.get_input(lesson.number, spec),
                        custom=lessons_store.is_custom(lesson.number, spec))

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

    @api.get("/lessons/{number}/content")
    def content(number: int) -> LessonContent:
        return _def_or_404(number).content()

    @api.get("/lessons/{number}/inputs")
    def inputs(number: int) -> list[InputOut]:
        lesson = _def_or_404(number)
        return [_input_out(lesson, spec) for spec in lesson.inputs]

    @api.put("/lessons/{number}/inputs/{input_id}")
    def save_input(number: int, input_id: str, body: InputIn) -> InputOut:
        lesson = _def_or_404(number)
        spec = _spec_or_404(lesson, input_id)
        try:
            lessons_store.save_input(number, spec, body.data)
        except ValidationError as exc:
            raise HTTPException(422, _validation_detail(exc)) from exc
        return _input_out(lesson, spec)

    @api.delete("/lessons/{number}/inputs/{input_id}")
    def reset_input(number: int, input_id: str) -> InputOut:
        lesson = _def_or_404(number)
        spec = _spec_or_404(lesson, input_id)
        lessons_store.reset_input(number, spec)
        return _input_out(lesson, spec)

    @api.post("/lessons/{number}/run")
    def run(number: int) -> LessonResult:
        lesson = _def_or_404(number)
        models = {spec.id: spec.model.model_validate(lessons_store.get_input(number, spec))
                  for spec in lesson.inputs}
        if lesson.requires_warehouse and not workspace.built:
            raise HTTPException(409, "Esta lección trabaja sobre el warehouse de NovaMercado: "
                                     "constrúyelo antes en «Datos de NovaMercado».")
        ctx = LessonContext(db_path=workspace.db_path, raw_dir=workspace.raw_dir,
                            stored_input=lessons_store.get_input)
        try:
            sections = lesson.compute(models, ctx)
        except ValueError as exc:  # entradas incoherentes: el mensaje ya es para el alumno
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # p. ej., una regla sobre una tabla que no existe
            raise HTTPException(400, f"La lección ha fallado con tus entradas: "
                                     f"{type(exc).__name__}: {exc}") from exc
        result = LessonResult(lesson=number, ran_at=datetime.now(UTC), sections=sections)
        lessons_store.save_result(result)
        return result

    @api.get("/lessons/{number}/result")
    def last_result(number: int) -> LessonResult | None:
        _def_or_404(number)
        return lessons_store.load_result(number)

    def _workspace_out() -> WorkspaceOut:
        return WorkspaceOut(status=workspace.status(),
                            json_schema=form_schema(WorkspaceSettings, WORKSPACE_LABELS))

    @api.get("/workspace")
    def get_workspace() -> WorkspaceOut:
        return _workspace_out()

    @api.put("/workspace/settings")
    def save_workspace_settings(body: InputIn) -> WorkspaceOut:
        try:
            workspace.save_settings(body.data)
        except ValidationError as exc:
            raise HTTPException(422, _validation_detail(exc)) from exc
        return _workspace_out()

    @api.delete("/workspace/settings")
    def reset_workspace_settings() -> WorkspaceOut:
        workspace.save_settings(WorkspaceSettings().model_dump())
        return _workspace_out()

    @api.post("/workspace/build")
    def build_workspace() -> WorkspaceOut:
        workspace.build()
        return _workspace_out()

    @api.delete("/workspace")
    def reset_workspace() -> WorkspaceOut:
        workspace.reset()
        return _workspace_out()

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
