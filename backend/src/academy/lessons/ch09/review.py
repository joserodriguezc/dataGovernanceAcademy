"""Linter de arquitectura con los estándares de la lección 9 y la política de la lección 6."""

from pathlib import Path

from academy.core.config import load_yaml
from academy.lessons.ch06.classify import ClassificationPolicy

from .lint import Linter, StandardsInput

LESSON_DIR = Path(__file__).parent
CH06_POLICY = LESSON_DIR.parent / "ch06" / "inputs" / "classification.yaml"


def make_linter(standards: StandardsInput | None = None,
                policy: ClassificationPolicy | None = None) -> Linter:
    """Sin argumentos usa los valores por defecto; la lección pasa los del alumno."""
    std = standards or StandardsInput.model_validate(
        load_yaml(LESSON_DIR / "inputs" / "standards.yaml"))
    return Linter(std, policy or ClassificationPolicy.model_validate(load_yaml(CH06_POLICY)))
