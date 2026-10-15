"""Orquestador del pipeline nocturno con registro de ejecuciones y de auditoría.

Ejecuta las lecciones que mantienen el warehouse (carga, golden record, metadatos, linaje y
calidad) en orden de dependencias, con las entradas que haya dejado el alumno en cada una. Si
un paso falla, se reintenta una vez; si vuelve a fallar, los pasos que dependen de él se
omiten. Cada paso queda registrado (quién, cuándo, cuánto tardó y cómo terminó) en una base
de operaciones aparte del warehouse, para que el historial sobreviva a cada reconstrucción.
"""

import getpass
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import duckdb

from academy.core.paths import OPS_DB, RAW_DIR, WAREHOUSE_DB
from academy.core.warehouse import build_warehouse, connect
from academy.lessons.base import LessonContext

from .config import Step

StepFn = Callable[[Path, Path, Path | None], object]


def lesson_steps(ctx: LessonContext) -> dict[str, StepFn]:
    """Funciones de cada paso: la carga y las lecciones 10, 6, 7 y 8."""
    def lesson(number: int) -> StepFn:
        def run(db: Path, raw: Path, out: Path | None) -> object:
            from academy.lessons.registry import LESSONS  # diferido: el registro nos importa

            definition = LESSONS[number]
            return definition.compute(
                {s.id: ctx.input_of(number, s) for s in definition.inputs}, ctx)
        return run

    return {
        "load": lambda db, raw, out: build_warehouse(db, raw),
        "pdm": lesson(10),
        "metadata": lesson(6),
        "lineage": lesson(7),
        "quality": lesson(8),
    }


def ops_connect(path: Path = OPS_DB) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR, step VARCHAR, attempt INTEGER, started_at TIMESTAMP,
        finished_at TIMESTAMP, seconds DOUBLE, status VARCHAR, error VARCHAR,
        executed_by VARCHAR)""")
    con.execute("""CREATE TABLE IF NOT EXISTS row_counts (
        run_id VARCHAR, measured_at TIMESTAMP, table_fqn VARCHAR, row_count BIGINT)""")
    return con


def run_pipeline(steps: list[Step], db: Path = WAREHOUSE_DB, raw: Path = RAW_DIR,
                 ops_db: Path = OPS_DB, out: Path | None = None,
                 functions: dict[str, StepFn] | None = None) -> tuple[str, dict[str, str]]:
    """Ejecuta el pipeline y devuelve (run_id, estado de cada paso)."""
    functions = functions or lesson_steps(LessonContext(db_path=db, raw_dir=raw))
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    user = getpass.getuser()
    status: dict[str, str] = {}
    with ops_connect(ops_db) as ops:
        for step in steps:
            if any(status.get(d) != "ok" for d in step.depends_on):
                status[step.id] = "omitido"
                ops.execute("INSERT INTO runs VALUES (?, ?, 0, ?, ?, 0, 'omitido', ?, ?)",
                            [run_id, step.id, datetime.now(), datetime.now(),
                             "depende de un paso que no terminó", user])
                continue
            for attempt in (1, 2):
                started = datetime.now()
                error = None
                try:
                    functions[step.id](db, raw, out)
                    result = "ok"
                except Exception as exc:  # noqa: BLE001 - se registra cualquier fallo
                    result, error = "fallido", f"{type(exc).__name__}: {exc}"[:500]
                finished = datetime.now()
                ops.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [run_id, step.id, attempt, started, finished,
                             (finished - started).total_seconds(), result, error, user])
                if result == "ok":
                    break
            status[step.id] = result
        if status.get("load") == "ok" and db.exists():  # observabilidad de volumen
            with connect(db, read_only=True) as con:
                tables = [r[0] for r in con.execute(
                    "SELECT schema_name || '.' || table_name FROM duckdb_tables() "
                    "WHERE schema_name = 'curated' ORDER BY 1").fetchall()]
                counts = [(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
                          for t in tables]
            ops.executemany("INSERT INTO row_counts VALUES (?, ?, ?, ?)",
                            [[run_id, datetime.now(), t, n] for t, n in counts])
    return run_id, status
