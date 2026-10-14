# Data Governance Academy

Plataforma de aprendizaje local que convierte *Data Governance Handbook* (Wendy S. Batchelder, Packt 2024) en **17 lecciones interactivas**, una por capítulo. Todas se aplican a la misma empresa ficticia: **NovaMercado**, un retail omnicanal, y su filial financiera regulada **NovaPay**.

Es la evolución de [dataGovernanceLab](https://github.com/joserodriguezc/dataGovernanceLab), donde cada capítulo es un microproyecto que se ejecuta desde la terminal. Aquí los mismos microproyectos se siguen desde el navegador: se editan las entradas, se ejecutan y se exploran los resultados.

> El libro no se incluye ni se reproduce: solo se referencia. Los resúmenes de las lecciones están escritos con palabras propias. Ver [docs/README.md](docs/README.md).

## Cómo es cada lección

| Sección | Qué haces |
|---|---|
| **Conceptos** | Lees las ideas del capítulo y cómo se aplican a NovaMercado |
| **Entradas** | Editas los datos de partida en formularios, o vuelves a los valores originales |
| **Ejecutar** | Lanzas el microproyecto del capítulo |
| **Resultados** | Exploras tablas, gráficos e informes interactivos |
| **Qué probar** | Haces retos guiados: cambias algo, vuelves a ejecutar y explicas qué ha cambiado |

Cada lección indica qué capítulos conviene completar antes, pero ninguno está bloqueado. El progreso se guarda en tu máquina, en `data/progress.json`.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 solo)
- [Node.js](https://nodejs.org/) 20 o superior, con npm

## Arrancar la app

**Para usarla** (un solo servidor en http://127.0.0.1:8000):

```bash
cd frontend && npm install && npm run build   # compila la interfaz (solo la primera vez o tras cambios)
cd ../backend && uv run academy               # sirve la API y la interfaz
```

**Para desarrollar** (recarga automática), en dos terminales:

```bash
cd backend && uv run uvicorn academy.api:app --reload   # API en el puerto 8000
cd frontend && npm run dev                              # interfaz en http://localhost:5173
```

## Paso a paso

Este recorrido crece con cada avance del proyecto.

| Paso | Qué se añade | Estado |
|---|---|---|
| 1 | Esqueleto: catálogo de las 17 lecciones, navegación, progreso y la API | ✅ hecho |
| 2 | Infraestructura de lecciones y lección 1 interactiva | ✅ hecho |
| 3 | Datos de NovaMercado en la app y lección 8 (técnica) | ⬜ siguiente |
| 4+ | Resto de capítulos, uno a uno | ⬜ pendiente |

### Paso 1. Esqueleto de la plataforma

- **Qué hay:** la página de inicio con las 17 lecciones agrupadas en las 4 partes del libro, el progreso (completadas / 17) y un botón para continuar por la siguiente lección pendiente. Cada lección tiene su ficha (capítulo del libro, microproyecto, resumen y recomendaciones previas), las cinco secciones, navegación anterior/siguiente y el botón para marcarla como completada.
- **Qué mirar:** abre la lección 8. Te avisa de que conviene completar antes la 6 y la 7. Márcalas como completadas y vuelve: el aviso desaparece.
- **Qué probar:** marca algunas lecciones, para el servidor y vuelve a arrancarlo. El progreso se mantiene. "Reiniciar progreso", en el inicio, lo borra.
- Las lecciones aparecen como "contenido en preparación" hasta que se migran del laboratorio.

### Paso 2. Lección 1 interactiva: ¿Qué es el gobierno de datos?

- **Qué hay:** la primera lección completa, con sus cinco secciones:
  - **Conceptos:** las ideas del capítulo y cómo se aplican.
  - **Entradas:** cinco formularios (programa, data equity, caso de negocio, política y scorecard) que se generan solos a partir de los modelos del laboratorio, con etiquetas en español. Un punto marca lo que has modificado y puedes volver a los valores originales.
  - **Ejecutar:** lanza el microproyecto con tus entradas.
  - **Resultados:** indicadores, avisos, el gráfico interactivo del flujo de caja, tablas y los cinco documentos (charter, data equity, caso de negocio, política y scorecard), que se leen en la app y se descargan en Markdown.
  - **Qué probar:** cuatro retos guiados.
- **Qué mirar:** ejecuta la lección y compara con el laboratorio: los números coinciden (data equity de −US$ 1,08 M, VAN de la opción preferida de US$ 2,25 M y payback en el mes 21).
- **Qué probar:** el reto 4. Sube la tasa de descuento a 0,20, guarda y vuelve a ejecutar. Resultados te avisa de que las entradas han cambiado desde la última ejecución, y el VAN de las opciones lentas cae más que el de las rápidas.
- La sección activa queda en la URL (`/leccion/1?seccion=resultados`), así que se puede enlazar y volver atrás con el navegador.

## Comandos útiles

```bash
cd backend && uv run pytest          # tests de la API y de las lecciones
cd backend && uv run ruff check .    # lint de Python
cd frontend && npm run lint          # lint del frontend (oxlint)
cd frontend && npm run build         # compilar la interfaz (incluye la comprobación de tipos)
```

## Estructura

```
dataGovernanceAcademy/
├── PLAN.md                  # plan de la migración del laboratorio a la app
├── backend/                 # uv · FastAPI
│   ├── src/academy/
│   │   ├── lessons.yaml     # catálogo de lecciones (resúmenes propios)
│   │   ├── catalog.py       # modelo y validación del catálogo
│   │   ├── progress.py      # progreso del alumno (JSON local)
│   │   ├── blocks.py        # bloques de resultado (indicadores, tablas, gráficos, documentos)
│   │   ├── schema.py        # JSON Schema de las entradas con etiquetas en español
│   │   ├── state.py         # entradas editadas y último resultado de cada lección
│   │   ├── core/            # utilidades compartidas traídas del laboratorio
│   │   ├── lessons/         # una carpeta por lección (lógica del laboratorio + lesson.py + content.yaml)
│   │   └── api.py           # API /api/... y servidor del frontend compilado
│   └── tests/
├── frontend/                # Vite · React · TypeScript
│   └── src/ (api.ts, App.tsx, pages/, components/InputsPanel.tsx, components/ResultView.tsx)
├── data/                    # estado local (gitignored)
└── docs/                    # tu copia del libro (gitignored)
```
