import { lazy, Suspense } from 'react'
import { Link, Route, Routes, useParams } from 'react-router-dom'
import Home from './pages/Home.tsx'

// La lección trae formularios y gráficos: se carga solo al abrir una lección.
const LessonPage = lazy(() => import('./pages/Lesson.tsx'))

// La key hace que cada lección empiece con su propio estado al navegar entre capítulos.
function LessonRoute() {
  const number = Number(useParams().number)
  return (
    <Suspense fallback={<p className="muted">Cargando lección…</p>}>
      <LessonPage key={number} number={number} />
    </Suspense>
  )
}

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <img src="/favicon.svg" alt="" width={24} height={24} />
          Data Governance Academy
        </Link>
        <span className="topbar-note">
          Basada en <em>Data Governance Handbook</em> (W. S. Batchelder, Packt 2024)
        </span>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/leccion/:number" element={<LessonRoute />} />
          <Route path="*" element={<p>Página no encontrada. <Link to="/">Volver al inicio</Link></p>} />
        </Routes>
      </main>
    </div>
  )
}
