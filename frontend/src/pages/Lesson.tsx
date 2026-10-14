import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  api, KIND_LABEL, type LessonContent, type LessonInput, type LessonOut, type LessonResult,
  type WorkspaceStatus,
} from '../api.ts'
import InputsPanel from '../components/InputsPanel.tsx'
import ResultView from '../components/ResultView.tsx'
import { ApiDown } from './Home.tsx'

const SECTIONS = [
  { id: 'conceptos', title: 'Conceptos' },
  { id: 'entradas', title: 'Entradas' },
  { id: 'ejecutar', title: 'Ejecutar' },
  { id: 'resultados', title: 'Resultados' },
  { id: 'probar', title: 'Qué probar' },
] as const
type SectionId = (typeof SECTIONS)[number]['id']

// Para las lecciones que aún no se han migrado del laboratorio.
const PLANNED_TEXT: Record<SectionId, string> = {
  conceptos: 'Las ideas del capítulo, explicadas con nuestras palabras, y cómo se aplican a NovaMercado.',
  entradas: 'Los datos de partida de la lección, editables desde formularios, con la opción de volver a los valores originales.',
  ejecutar: 'Lanza el microproyecto del capítulo con tus entradas.',
  resultados: 'Tablas, gráficos e informes interactivos generados con tus entradas.',
  probar: 'Retos guiados: cambia una entrada, vuelve a ejecutar y explica qué ha cambiado.',
}

interface Interactive {
  content: LessonContent
  inputs: LessonInput[]
  result: LessonResult | null
  workspace: WorkspaceStatus | null // solo si la lección usa el warehouse
}

export default function LessonPage({ number }: { number: number }) {
  const [data, setData] = useState<LessonOut | null>(null)
  const [live, setLive] = useState<Interactive | null>(null)
  const [error, setError] = useState<string | null>(null)
  // La sección activa vive en la URL (?seccion=...): se puede enlazar y volver atrás.
  const [params, setParams] = useSearchParams()
  const requested = params.get('seccion')
  const section: SectionId = SECTIONS.some((s) => s.id === requested)
    ? (requested as SectionId) : 'conceptos'
  const setSection = (id: SectionId) => setParams(id === 'conceptos' ? {} : { seccion: id })
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [stale, setStale] = useState(false) // hay entradas guardadas después del último resultado

  useEffect(() => {
    api.lesson(number)
      .then(async (out) => {
        setData(out)
        if (out.lesson.status !== 'available') return
        const [content, inputs, result, workspace] = await Promise.all([
          api.content(number), api.inputs(number), api.result(number),
          out.lesson.requires_warehouse ? api.workspace().then((w) => w.status) : null,
        ])
        setLive({ content, inputs, result, workspace })
      })
      .catch((e: Error) => setError(e.message))
  }, [number])

  if (error) return <ApiDown message={error} />
  if (!data) return <p className="muted">Cargando lección…</p>

  const { lesson, state } = data

  async function toggle() {
    const states = await api.setCompleted(lesson.number, !state.completed)
    setData((d) => (d ? { ...d, state: states.find((s) => s.number === lesson.number)! } : d))
  }

  async function run() {
    setRunning(true)
    setRunError(null)
    try {
      const result = await api.run(lesson.number)
      setLive((l) => (l ? { ...l, result } : l))
      setStale(false)
      setSection('resultados')
    } catch (e) {
      setRunError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  function inputChanged(input: LessonInput) {
    setLive((l) => (l ? { ...l, inputs: l.inputs.map((i) => (i.id === input.id ? input : i)) } : l))
    setStale(true)
  }

  return (
    <article className="lesson">
      <nav className="breadcrumb"><Link to="/">Lecciones</Link> / Capítulo {lesson.number}</nav>
      <header className="lesson-head">
        <div className="card-head">
          <span className="chapter">Capítulo {lesson.number} · Parte {lesson.part}</span>
          <span className={`badge kind-${lesson.kind}`}>{KIND_LABEL[lesson.kind]}</span>
        </div>
        <h1>{lesson.title}</h1>
        <p className="muted">Libro: <em>{lesson.book_title}</em> · Microproyecto: {lesson.project}</p>
        <p className="lead">{lesson.summary}</p>
      </header>

      {state.missing_recommended.length > 0 && (
        <div className="notice">
          Conviene completar antes:{' '}
          {state.missing_recommended.map((n, i) => (
            <span key={n}>{i > 0 && ', '}<Link to={`/leccion/${n}`}>capítulo {n}</Link></span>
          ))}
          . Puedes seguir igualmente.
        </div>
      )}

      <div className="tabs" role="tablist">
        {SECTIONS.map((s) => (
          <button key={s.id} role="tab" aria-selected={s.id === section}
                  className={s.id === section ? 'tab active' : 'tab'}
                  onClick={() => setSection(s.id)}>
            {s.title}
          </button>
        ))}
      </div>
      <section className="panel" role="tabpanel">
        {lesson.status !== 'available' || !live
          ? <Planned section={section} number={lesson.number} loading={lesson.status === 'available'} />
          : section === 'conceptos' ? <Concepts content={live.content} />
          : section === 'entradas' ? <InputsPanel lesson={lesson.number} inputs={live.inputs} onChange={inputChanged} />
          : section === 'ejecutar' ? (
            <div className="run">
              <p>
                Ejecuta el microproyecto con las entradas actuales
                {live.inputs.some((i) => i.custom) ? ' (incluye tus cambios)' : ' (valores originales)'}.
              </p>
              {live.workspace && !live.workspace.built && (
                <div className="notice">
                  Esta lección trabaja sobre el warehouse de NovaMercado y todavía no está construido.{' '}
                  <Link to="/datos">Constrúyelo en «Datos de NovaMercado»</Link> y vuelve.
                </div>
              )}
              {live.workspace?.pending_changes && (
                <div className="notice">
                  Has cambiado los parámetros de los datos sin reconstruir: la lección usará los datos anteriores.{' '}
                  <Link to="/datos">Reconstruir</Link>
                </div>
              )}
              {live.workspace?.built && live.workspace.built_with && (
                <p className="muted">
                  Datos: {String(live.workspace.built_with.persons)} clientes, semilla {String(live.workspace.built_with.seed)}.{' '}
                  <Link to="/datos">Cambiar</Link>
                </p>
              )}
              <button className="button primary large" onClick={run}
                      disabled={running || (live.workspace !== null && !live.workspace.built)}>
                {running ? 'Ejecutando…' : '▶ Ejecutar la lección'}
              </button>
              {runError && <div className="notice bad" role="alert">{runError}</div>}
              {live.result && (
                <p className="muted">
                  Última ejecución: {new Date(live.result.ran_at).toLocaleString('es-ES')}.{' '}
                  <button className="link" onClick={() => setSection('resultados')}>Ver resultados</button>
                </p>
              )}
            </div>
          )
          : section === 'resultados' ? (
            live.result ? (
              <>
                {stale && (
                  <div className="notice">
                    Has cambiado entradas después de esta ejecución.{' '}
                    <button className="link" onClick={run} disabled={running}>Volver a ejecutar</button>
                  </div>
                )}
                <ResultView result={live.result} />
              </>
            ) : (
              <p>
                Todavía no hay resultados.{' '}
                <button className="link" onClick={run} disabled={running}>Ejecuta la lección</button>.
              </p>
            )
          )
          : <Challenges content={live.content} />}
      </section>

      <footer className="lesson-foot">
        {data.previous
          ? <Link className="button" to={`/leccion/${data.previous}`}>← Capítulo {data.previous}</Link>
          : <span />}
        <button className={state.completed ? 'button' : 'button primary'} onClick={toggle}>
          {state.completed ? '✓ Completada · desmarcar' : 'Marcar como completada'}
        </button>
        {data.next
          ? <Link className="button" to={`/leccion/${data.next}`}>Capítulo {data.next} →</Link>
          : <span />}
      </footer>
    </article>
  )
}

function Planned({ section, number, loading }: { section: SectionId; number: number; loading: boolean }) {
  if (loading) return <p className="muted">Cargando…</p>
  return (
    <>
      <p>{PLANNED_TEXT[section]}</p>
      <p className="muted">
        Esta lección todavía se está migrando del laboratorio. Mientras tanto puedes seguirla en el
        repositorio <em>dataGovernanceLab</em>, en la carpeta del capítulo {number}.
      </p>
    </>
  )
}

function Concepts({ content }: { content: LessonContent }) {
  return (
    <div className="concepts">
      <p className="lead">{content.intro}</p>
      <h3>Ideas del capítulo y cómo las aplicamos</h3>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Idea</th><th>En la lección</th></tr></thead>
          <tbody>
            {content.ideas.map((i) => (
              <tr key={i.idea}><td>{i.idea}</td><td>{i.application}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {content.takeaways.length > 0 && (
        <>
          <h3>Qué te llevas</h3>
          <ul>{content.takeaways.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
    </div>
  )
}

function Challenges({ content }: { content: LessonContent }) {
  return (
    <div className="challenges">
      <p className="muted">Cambia una entrada, vuelve a ejecutar y explica qué ha pasado.</p>
      {content.challenges.map((c, n) => (
        <div key={c.title} className="challenge">
          <h3><span className="part-number">Reto {n + 1}</span> {c.title}</h3>
          <ol>{c.steps.map((s) => <li key={s}>{s}</li>)}</ol>
          <p><strong>Qué observar:</strong> {c.look_for}</p>
        </div>
      ))}
    </div>
  )
}
