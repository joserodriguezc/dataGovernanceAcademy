import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, KIND_LABEL, type LessonOut } from '../api.ts'
import { ApiError } from './Home.tsx'

// Secciones de cada lección. Se activan a medida que cada capítulo se migra del laboratorio.
const SECTIONS = [
  { id: 'conceptos', title: 'Conceptos', text: 'Las ideas del capítulo, explicadas con nuestras palabras, y cómo se aplican a NovaMercado.' },
  { id: 'entradas', title: 'Entradas', text: 'Los datos de partida de la lección, editables desde formularios, con la opción de volver a los valores originales.' },
  { id: 'ejecutar', title: 'Ejecutar', text: 'Lanza el microproyecto del capítulo y sigue su progreso.' },
  { id: 'resultados', title: 'Resultados', text: 'Tablas, gráficos e informes interactivos generados con tus entradas.' },
  { id: 'probar', title: 'Qué probar', text: 'Retos guiados: cambia una entrada, vuelve a ejecutar y explica qué ha cambiado.' },
] as const

export default function LessonPage({ number }: { number: number }) {
  const [data, setData] = useState<LessonOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [section, setSection] = useState<string>(SECTIONS[0].id)

  useEffect(() => {
    api.lesson(number).then(setData).catch((e: Error) => setError(e.message))
  }, [number])

  if (error) return <ApiError message={error} />
  if (!data) return <p className="muted">Cargando lección…</p>

  const { lesson, state } = data
  const current = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0]

  async function toggle() {
    const states = await api.setCompleted(lesson.number, !state.completed)
    setData((d) => (d ? { ...d, state: states.find((s) => s.number === lesson.number)! } : d))
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
        <h2>{current.title}</h2>
        <p>{current.text}</p>
        {lesson.status === 'planned' && (
          <p className="muted">
            Esta lección todavía se está migrando del laboratorio. Mientras tanto puedes seguirla
            en el repositorio <em>dataGovernanceLab</em>, en la carpeta del capítulo {lesson.number}.
          </p>
        )}
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
