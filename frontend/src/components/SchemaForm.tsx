import Form from '@rjsf/core'
import type { RJSFSchema, WidgetProps } from '@rjsf/utils'
import validator from '@rjsf/validator-ajv8'
import type { FieldError } from '../api.ts'

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

interface Props {
  schema: Record<string, unknown>
  value: unknown
  dirty: boolean
  saving: boolean
  errors: FieldError[]
  saveLabel?: string
  onChange: (value: unknown) => void
  onSubmit: (value: unknown) => void
  onDiscard: () => void
}

/** Formulario generado desde el JSON Schema de un modelo pydantic. La validación la hace el
 *  backend (pydantic) y sus errores se muestran arriba, con la ruta de cada campo. */
export default function SchemaForm({
  schema, value, dirty, saving, errors, saveLabel = 'Guardar cambios', onChange, onSubmit, onDiscard,
}: Props) {
  return (
    <>
      {errors.length > 0 && (
        <div className="notice bad" role="alert">
          <strong>Revisa estos campos:</strong>
          <ul>{errors.map((e) => <li key={e.loc + e.msg}><code>{e.loc || 'general'}</code>: {e.msg}</li>)}</ul>
        </div>
      )}
      <Form
        schema={schema as RJSFSchema}
        formData={value}
        validator={validator}
        widgets={{ TextWidget: AutoTextWidget }}
        noHtml5Validate
        noValidate
        showErrorList={false}
        onChange={(e) => onChange(e.formData)}
        onSubmit={(e) => onSubmit(e.formData)}
      >
        <div className="form-actions">
          <button type="submit" className="button primary" disabled={saving || !dirty}>
            {saving ? 'Guardando…' : saveLabel}
          </button>
          {dirty && <button type="button" className="button" onClick={onDiscard}>Descartar cambios</button>}
        </div>
      </Form>
    </>
  )
}
