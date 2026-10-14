import { useState } from 'react'
import { api, ApiError, type FieldError, type LessonInput } from '../api.ts'
import SchemaForm from './SchemaForm.tsx'

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const copy = { ...record }
  delete copy[key]
  return copy
}

interface Props {
  lesson: number
  inputs: LessonInput[]
  onChange: (input: LessonInput) => void
}

export default function InputsPanel({ lesson, inputs, onChange }: Props) {
  const [active, setActive] = useState(inputs[0]?.id)
  const current = inputs.find((i) => i.id === active) ?? inputs[0]
  // Borrador por entrada: se conserva al cambiar de sub-pestaña.
  const [drafts, setDrafts] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<FieldError[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!current) return <p className="muted">Esta lección no tiene entradas editables.</p>

  function select(id: string) {
    setActive(id)
    setErrors([])
    setMessage(null)
  }

  async function save(data: unknown) {
    setSaving(true)
    setErrors([])
    setMessage(null)
    try {
      const saved = await api.saveInput(lesson, current.id, data)
      setDrafts((d) => without(d, current.id))
      onChange(saved)
      setMessage('Guardado. Vuelve a ejecutar la lección para ver el efecto.')
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) setErrors(e.fields)
      else setMessage(`No se pudo guardar: ${(e as Error).message}`)
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    if (!confirm(`¿Volver a los valores originales de «${current.title}»?`)) return
    const original = await api.resetInput(lesson, current.id)
    setDrafts((d) => without(d, current.id))
    setErrors([])
    onChange(original)
    setMessage('Restablecidos los valores originales.')
  }

  return (
    <div className="inputs">
      {inputs.length > 1 && (
        <div className="subtabs" role="tablist">
          {inputs.map((i) => (
            <button key={i.id} role="tab" aria-selected={i.id === current.id}
                    className={i.id === current.id ? 'subtab active' : 'subtab'}
                    onClick={() => select(i.id)}>
              {i.title}
              {(i.custom || i.id in drafts) && <span className="dot" title="Modificado" />}
            </button>
          ))}
        </div>
      )}
      <p className="muted">{current.description}</p>
      {current.custom && (
        <p className="tag-line">
          Estás usando valores editados.{' '}
          <button className="link" onClick={reset}>Volver a los originales</button>
        </p>
      )}
      {message && <p className="tag-line" role="status">{message}</p>}
      <SchemaForm
        key={current.id}
        schema={current.json_schema}
        value={drafts[current.id] ?? current.data}
        dirty={current.id in drafts}
        saving={saving}
        errors={errors}
        onChange={(v) => setDrafts((d) => ({ ...d, [current.id]: v }))}
        onSubmit={save}
        onDiscard={() => setDrafts((d) => without(d, current.id))}
      />
    </div>
  )
}
