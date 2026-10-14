"""Utilidades de fechas compartidas por los capítulos."""

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    """Suma meses manteniendo el día cuando existe (31/01 + 1 mes = 28/02 o 29/02)."""
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
