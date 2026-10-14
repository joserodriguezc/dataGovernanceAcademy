import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, KIND_LABEL, type CatalogOut } from '../api.ts'

export default function Home() {
  const [catalog, setCatalog] = useState<CatalogOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.catalog().then(setCatalog).catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <ApiDown message={error} />
  if (!catalog) return <p className="muted">Cargando lecciones…</p>

  const states = new Map(catalog.states.map((s) => [s.number, s]))
  const done = catalog.states.filter((s) => s.completed).length
  const total = catalog.lessons.length
  const nextLesson = catalog.lessons.find((l) => !states.get(l.number)?.completed)

  async function reset() {
    if (!confirm('¿Borrar todo el progreso?')) return
    const newStates = await api.resetProgress()
    setCatalog((c) => (c ? { ...c, states: newStates } : c))
  }

  return (
    <>
      <section className="hero">
        <div>
          <h1>Aprende gobierno de datos haciendo</h1>
          <p className="lead">
            Un recorrido por los 17 capítulos del libro, cada uno convertido en una lección
            práctica sobre NovaMercado, un retail ficticio, y su filial financiera NovaPay.
          </p>
          {nextLesson && (
            <Link className="button primary" to={`/leccion/${nextLesson.number}`}>
              {done === 0 ? 'Empezar' : 'Continuar'} con la lección {nextLesson.number}
            </Link>
          )}
        </div>
        <div className="progress-card" aria-label="Progreso">
          <span className="progress-value">{done}<small> / {total}</small></span>
          <span className="muted">lecciones completadas</span>
          <div className="meter"><div style={{ width: `${(done / total) * 100}%` }} /></div>
          {done > 0 && <button className="link" onClick={reset}>Reiniciar progreso</button>}
        </div>
      </section>

      {Object.entries(catalog.parts).map(([part, name]) => (
        <section key={part} className="part">
          <h2><span className="part-number">Parte {part}</span> {name}</h2>
          <div className="grid">
            {catalog.lessons.filter((l) => String(l.part) === part).map((lesson) => {
              const state = states.get(lesson.number)
              return (
                <Link key={lesson.number} to={`/leccion/${lesson.number}`}
                      className={`card${state?.completed ? ' completed' : ''}`}>
                  <div className="card-head">
                    <span className="chapter">Capítulo {lesson.number}</span>
                    <span className={`badge kind-${lesson.kind}`}>{KIND_LABEL[lesson.kind]}</span>
                  </div>
                  <h3>{lesson.title}</h3>
                  <p className="muted">{lesson.project}</p>
                  <div className="card-foot">
                    {state?.completed
                      ? <span className="status done">✓ Completada</span>
                      : lesson.status === 'planned'
                        ? <span className="status">Contenido en preparación</span>
                        : <span className="status ready">Lista para hacer</span>}
                  </div>
                </Link>
              )
            })}
          </div>
        </section>
      ))}
    </>
  )
}

export function ApiDown({ message }: { message: string }) {
  return (
    <div className="notice">
      <strong>No se puede conectar con la API</strong> ({message}). Arranca el backend con{' '}
      <code>uv run academy</code> desde la carpeta <code>backend</code>.
    </div>
  )
}
