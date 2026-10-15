"""Lecciones interactivas disponibles. Una lección migrada del laboratorio se añade aquí."""

from academy.lessons.base import LessonDef
from academy.lessons.ch01.lesson import LESSON as CH01
from academy.lessons.ch02.lesson import LESSON as CH02
from academy.lessons.ch03.lesson import LESSON as CH03
from academy.lessons.ch04.lesson import LESSON as CH04
from academy.lessons.ch05.lesson import LESSON as CH05
from academy.lessons.ch06.lesson import LESSON as CH06
from academy.lessons.ch07.lesson import LESSON as CH07
from academy.lessons.ch08.lesson import LESSON as CH08
from academy.lessons.ch09.lesson import LESSON as CH09
from academy.lessons.ch10.lesson import LESSON as CH10
from academy.lessons.ch11.lesson import LESSON as CH11

LESSONS: dict[int, LessonDef] = {
    lesson.number: lesson
    for lesson in [CH01, CH02, CH03, CH04, CH05, CH06, CH07, CH08, CH09, CH10, CH11]
}
