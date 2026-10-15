# Plan: del laboratorio a Data Governance Academy

## Objetivo

Convertir los 17 microproyectos de [dataGovernanceLab](https://github.com/joserodriguezc/dataGovernanceLab) en una **plataforma de aprendizaje local**: una lección interactiva por capítulo del libro, que se sigue desde el navegador.

Decisiones:
- **Para qué:** aprender. Es un recorrido guiado por el libro, no una herramienta de gobierno para producción.
- **Stack:** backend con FastAPI (Python 3.12, uv) y frontend con React (Vite, TypeScript).
- **Despliegue:** local y de un solo usuario. El estado se guarda en `data/`.
- **Libro:** se referencia, nunca se reproduce. Los resúmenes son propios.
- **Laboratorio:** se queda como está, como referencia (v1). La app trae su código lección a lección.

## Arquitectura

```
navegador (React) ──/api──▶ FastAPI ──▶ lecciones (lógica del laboratorio) ──▶ DuckDB local
```

- **Catálogo:** `lessons.yaml` describe las 17 lecciones (parte, tipo, microproyecto, resumen y recomendaciones previas).
- **Lección migrada:** cada capítulo del laboratorio se separa en tres piezas:
  - **`inputs`:** los modelos pydantic del laboratorio. Su JSON Schema genera los formularios en el frontend.
  - **`compute(inputs) -> Result`:** los cálculos del capítulo, que devuelven datos estructurados en lugar de escribir archivos.
  - **`render(result)`:** los informes Markdown o HTML, que se siguen generando para descargarlos.
- **Gráficos:** en el navegador, a partir del `Result` (sin PNG). El linaje usa un grafo interactivo.
- **Tests:** los del laboratorio vienen con cada lección, para garantizar que la app da los mismos números.

## Pasos

| Paso | Contenido | Criterio de hecho | Estado |
|---|---|---|---|
| 1 | Esqueleto: monorepo, catálogo, progreso, API, inicio y ficha de lección | Tests de la API en verde, el frontend compila y `uv run academy` sirve la app | ✅ hecho |
| 2 | Infraestructura de lecciones: registro de lecciones, entradas con JSON Schema, ejecución y resultados; piloto con el capítulo 1 | La lección 1 se edita, se ejecuta y muestra sus resultados con los mismos números que el laboratorio | ✅ hecho |
| 3 | Datos compartidos: generador sintético y warehouse de NovaMercado desde la app; piloto técnico con el capítulo 8 (y lo que necesita del 6 y el 7) | La lección 8 construye su warehouse y muestra reglas, incidencias y certificación | ✅ hecho |
| 4 | Capítulos 2 a 5 (gestión) | Cada lección con sus cinco secciones y sus tests | ✅ hecho |
| 5 | Capítulos 6, 7, 9, 10 y 11 (técnicos), con el grafo de linaje interactivo | Ídem; con 6 y 7 ejecutadas, la lección 8 certifica `curated.dim_store` como en el laboratorio | ✅ hecho |
| 6 | Capítulos 12 a 16 | Ídem | ⬜ |
| 7 | Capítulo 17: caso NovaPay de punta a punta | Ídem | ⬜ |
| 8 | Pulido: retos de "Qué probar" con comprobación automática y descarga de informes | — | ⬜ |

## Cómo se migra una lección

1. Copiar la lógica del capítulo del laboratorio a `backend/src/academy/lessons/chNN/`, con sus `inputs/` y `templates/`. Los imports de `dglab` pasan a `academy.core`.
2. Escribir `lesson.py`: las `InputSpec` (modelo pydantic + YAML por defecto) y `compute(inputs) -> list[ResultSection]`, que devuelve bloques (`kpis`, `callout`, `table`, `line_chart`, `document`).
3. Escribir `content.yaml`: introducción, ideas (idea → cómo se aplica), qué te llevas, retos y etiquetas en español de los campos.
4. Registrar la lección en `lessons/registry.py`.
5. Traer los tests del laboratorio a `backend/tests/lessons/` y añadir uno que compruebe que `compute` da los mismos números que el laboratorio.

Si la lección usa entradas de otra lección, las lee con `ctx.input_of(número, spec)`: obtiene lo que haya editado el alumno o, si no ha editado nada, los valores por defecto. Cada campo de los formularios necesita su etiqueta en español, en `content.yaml` o en `labels.yaml`, y un test lo comprueba.

Las herramientas de línea de comandos del laboratorio (marketplace, impact, review, lookup) no se traen: su función la cubre la interfaz. De esos módulos solo se conservan las funciones que reutilizan las lecciones.

Si la lección usa el warehouse, se marca con `requires_warehouse=True` y su `compute` recibe un `LessonContext` con `db_path` y `raw_dir`. La API responde 409 si el warehouse no está construido. En los tests se usa el fixture `small_workspace` (tests/conftest.py).

Cada paso termina con un commit, su entrada en el "Paso a paso" del README y su estado actualizado en esta tabla.
