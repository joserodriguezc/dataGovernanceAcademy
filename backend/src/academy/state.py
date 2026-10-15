"""Estado de cada lección en disco: entradas editadas por el alumno y último resultado."""

import json
from pathlib import Path
from typing import Any

from academy.blocks import LessonResult
from academy.lessons.base import InputSpec


class LessonStore:
    def __init__(self, data_dir: Path):
        self.base = data_dir / "lessons"

    def _dir(self, lesson: int) -> Path:
        return self.base / f"ch{lesson:02d}"

    def _input_path(self, lesson: int, spec: InputSpec) -> Path:
        return self._dir(lesson) / "inputs" / f"{spec.id}.json"

    def is_custom(self, lesson: int, spec: InputSpec) -> bool:
        return self._input_path(lesson, spec).exists()

    def get_input(self, lesson: int, spec: InputSpec) -> dict[str, Any]:
        """Lo que ha editado el alumno o, si no ha editado nada, los valores por defecto."""
        path = self._input_path(lesson, spec)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return spec.default()

    def save_input(self, lesson: int, spec: InputSpec, data: dict[str, Any]) -> dict[str, Any]:
        """Valida con el modelo de la lección (lanza ValidationError) y guarda."""
        clean = spec.model.model_validate(data).model_dump(mode="json", by_alias=True)
        path = self._input_path(lesson, spec)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        return clean

    def reset_input(self, lesson: int, spec: InputSpec) -> None:
        self._input_path(lesson, spec).unlink(missing_ok=True)

    def save_result(self, result: LessonResult) -> None:
        path = self._dir(result.lesson) / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json(), encoding="utf-8")

    def load_result(self, lesson: int) -> LessonResult | None:
        path = self._dir(lesson) / "result.json"
        if not path.exists():
            return None
        return LessonResult.model_validate_json(path.read_text(encoding="utf-8"))
