import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type FieldError, type WorkspaceOut } from '../api.ts'
import SchemaForm from '../components/SchemaForm.tsx'
import { ApiDown } from './Home.tsx'

const LAYERS: Record<string, string> = {
  raw: 'Raw: tal como llega de cada sistema',
  staging: 'Staging: tipos correctos, sin corregir defectos',
  curated: 'Curated: modelo para el negocio',
  meta: 'Meta: lo que escriben las lecciones',
}
const number = new Intl.NumberFormat('es-ES')

export default function WorkspacePage() {
  const [ws, setWs] = useState<WorkspaceOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<unknown>(null)
  const [errors, setErrors] = useState<FieldError[]>([])
  const [busy, setBusy] = useState<'saving' | 'building' | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.workspace().then(setWs).catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <ApiDown message={error} />
  if (!ws) return <p className="muted">Cargando…</p>
  const { status } = ws

  async function act(kind: 'saving' | 'building', fn: () => Promise<WorkspaceOut>, done: string) {
    setBusy(kind)
    setErrors([])
    setMessage(null)
    try {
      setWs(await fn())
      setDraft(null)
      setMessage(done)
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) setErrors(e.fields)
      else setMessage(`No se pudo completar: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  const layers = Object.keys(LAYERS)
    .map((layer) => ({ layer, tables: status.tables.filter((t) => t.layer === layer) }))
    .filter((l) => l.tables.length > 0)

  return (
    <article className="lesson">
      <nav className="breadcrumb"><Link to="/">Lecciones</Link> / Datos de NovaMercado</nav>
      <header className="lesson-head">
        <h1>Datos de NovaMercado</h1>
        <p className="lead">
          Las lecciones técnicas trabajan sobre un warehouse con los datos sintéticos de NovaMercado:
          clientes en el CRM, el e-commerce y las tiendas, productos, proveedores y ventas. Los datos
          llevan defectos sembrados a propósito, y se guarda cuáles son para poder comprobar si las
          reglas los encuentran.
        </p>
      </header>

      <section className="panel standalone">
        <div className="status-row">
          <div>
            <h2>{status.built ? '✓ Warehouse construido' : 'Warehouse sin construir'}</h2>
            <p className="muted">
              {status.built && status.built_at
                ? `Construido el ${new Date(status.built_at).toLocaleString('es-ES')} con ${number.format(Number(status.built_with?.persons))} clientes y semilla ${String(status.built_with?.seed)}.`
                : 'Genera los datos y construye el warehouse para poder ejecutar las lecciones técnicas.'}
            </p>
          </div>
          <div className="actions">
            <button className="button primary large" disabled={busy !== null}
                    onClick={() => act('building', api.buildWorkspace, 'Warehouse construido. Las lecciones técnicas ya pueden ejecutarse sobre estos datos.')}>
              {busy === 'building' ? 'Construyendo… (unos segundos)' : status.built ? '↻ Reconstruir' : '▶ Generar y construir'}
            </button>
            {status.built && (
              <button className="button" disabled={busy !== null}
                      onClick={() => confirm('¿Borrar los datos y el warehouse? Los parámetros se conservan.')
                        && act('building', api.resetWorkspace, 'Datos borrados.')}>
                Borrar datos
              </button>
            )}
          </div>
        </div>
        {status.pending_changes && (
          <div className="notice">
            Has cambiado los parámetros después de construir. Reconstruye para que las lecciones usen los nuevos datos.
          </div>
        )}
        {message && <p className="tag-line" role="status">{message}</p>}

        {status.built && (
          <div className="ws-grid">
            <div>
              <h3>Tablas por capa</h3>
              {layers.map(({ layer, tables }) => (
                <details key={layer} open={layer !== 'raw'}>
                  <summary>{LAYERS[layer]} · {tables.length} tablas</summary>
                  <table>
                    <tbody>
                      {tables.map((t) => (
                        <tr key={t.table}><td><code>{t.table}</code></td><td className="right">{number.format(t.rows)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              ))}
            </div>
            <div>
              <h3>Defectos sembrados (solucionario)</h3>
              <table>
                <tbody>
                  {Object.entries(status.seeded_defects).map(([k, n]) => (
                    <tr key={k}><td><code>{k}</code></td><td className="right">{number.format(n)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="panel standalone inputs">
        <h2>Parámetros de los datos</h2>
        <p className="muted">
          Cambia la semilla, el volumen o la proporción de cada defecto, guarda y reconstruye.{' '}
          <button className="link" disabled={busy !== null}
                  onClick={() => act('saving', api.resetWorkspaceSettings, 'Parámetros originales restablecidos.')}>
            Volver a los parámetros originales
          </button>
        </p>
        <SchemaForm
          schema={ws.json_schema}
          value={draft ?? status.settings}
          dirty={draft !== null}
          saving={busy === 'saving'}
          errors={errors}
          saveLabel="Guardar parámetros"
          onChange={setDraft}
          onSubmit={(v) => act('saving', () => api.saveWorkspaceSettings(v), 'Parámetros guardados. Reconstruye para aplicarlos.')}
          onDiscard={() => setDraft(null)}
        />
      </section>
    </article>
  )
}
