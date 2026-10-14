import Form from '@rjsf/core'
import type { RJSFSchema, WidgetProps } from '@rjsf/utils'
import validator from '@rjsf/validator-ajv8'
import { useState } from 'react'
import { api, ApiError, type FieldError, type LessonInput } from '../api.ts'

// Los textos largos se editan en un área de texto; los cortos, en una línea.
function AutoTextWidget(props: WidgetProps) {
  const { id, value, required, disabled, readonly, onChange, onBlur, onFocus } = props
  const text = value ?? ''
  const common = {
    id, required, disabled, readOnly: readonly, value: text,
    onBlur: () => onBlur(id, text), onFocus: () => onFocus(id, text),
  }
  if (String(text).length > 70) {
    return <textarea {...common} rows={3}
                     onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)} />
  }
  return <input type="text" {...common}
                onChange={(e) => onChange(e.target.value === '' ? undefined : e.target.value)} />
}

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
  // Borrador del formulario por entrada: se conserva al cambiar de sub-pestaña.
  const [drafts, setDrafts] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<FieldError[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  if (!current) return <p className="muted">Esta lección no tiene entradas editables.</p>
  const draft = drafts[current.id] ?? current.data
  const dirty = current.id in drafts

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
      <p className="muted">{current.description}</p>
      {current.custom && (
        <p className="tag-line">
          Estás usando valores editados.{' '}
          <button className="link" onClick={reset}>Volver a los originales</button>
        </p>
      )}
      {errors.length > 0 && (
        <div className="notice bad" role="alert">
          <strong>Revisa estos campos:</strong>
          <ul>{errors.map((e) => <li key={e.loc + e.msg}><code>{e.loc || 'general'}</code>: {e.msg}</li>)}</ul>
        </div>
      )}
      {message && <p className="tag-line" role="status">{message}</p>}
      <Form
        key={current.id}
        schema={current.json_schema as RJSFSchema}
        formData={draft}
        validator={validator}
        widgets={{ TextWidget: AutoTextWidget }}
        noHtml5Validate
        noValidate
        showErrorList={false}
        onChange={(e) => setDrafts((d) => ({ ...d, [current.id]: e.formData }))}
        onSubmit={(e) => save(e.formData)}
      >
        <div className="form-actions">
          <button type="submit" className="button primary" disabled={saving || !dirty}>
            {saving ? 'Guardando…' : 'Guardar cambios'}
          </button>
          {dirty && (
            <button type="button" className="button"
                    onClick={() => setDrafts((d) => without(d, current.id))}>
              Descartar cambios
            </button>
          )}
        </div>
      </Form>
    </div>
  )
}
