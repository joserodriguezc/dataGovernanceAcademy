"""Progreso del alumno: lecciones completadas, guardadas en un JSON local (un solo usuario)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from academy.catalog import Catalog


class Progress(BaseModel):
    completed: dict[int, datetime] = {}  # número de lección → fecha en que se completó


class LessonState(BaseModel):
    number: int
    completed: bool
    completed_at: datetime | None
    missing_recommended: list[int]  # recomendadas antes que aún no se han completado


class ProgressStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Progress:
        if not self.path.exists():
            return Progress()
        return Progress.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, progress: Progress) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(progress.model_dump(mode="json"), indent=2),
                             encoding="utf-8")

    def set_completed(self, number: int, completed: bool) -> Progress:
        progress = self.load()
        if completed:
            progress.completed.setdefault(number, datetime.now(UTC))
        else:
            progress.completed.pop(number, None)
        self.save(progress)
        return progress

    def reset(self) -> None:
        self.path.unlink(missing_ok=True)


def lesson_states(catalog: Catalog, progress: Progress) -> list[LessonState]:
    return [
        LessonState(
            number=lesson.number,
            completed=lesson.number in progress.completed,
            completed_at=progress.completed.get(lesson.number),
            missing_recommended=[n for n in lesson.recommended if n not in progress.completed],
        )
        for lesson in catalog.lessons
    ]
