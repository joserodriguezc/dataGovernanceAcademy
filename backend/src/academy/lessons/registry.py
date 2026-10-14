"""Lecciones interactivas disponibles. Una lección migrada del laboratorio se añade aquí."""

from academy.lessons.base import LessonDef
from academy.lessons.ch01.lesson import LESSON as CH01

LESSONS: dict[int, LessonDef] = {lesson.number: lesson for lesson in [CH01]}
