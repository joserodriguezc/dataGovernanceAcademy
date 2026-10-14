// Tipos y cliente de la API (backend/src/academy/api.py).

export type LessonKind = 'gestion' | 'tecnico' | 'caso'

export interface Lesson {
  number: number
  slug: string
  title: string
  book_title: string
  part: number
  kind: LessonKind
  project: string
  summary: string
  recommended: number[]
  status: 'available' | 'planned'
  requires_warehouse: boolean
}

export interface LessonState {
  number: number
  completed: boolean
  completed_at: string | null
  missing_recommended: number[]
}

export interface CatalogOut {
  parts: Record<string, string>
  lessons: Lesson[]
  states: LessonState[]
}

export interface LessonOut {
  lesson: Lesson
  state: LessonState
  previous: number | null
  next: number | null
}

// --- Contenido, entradas y resultados de una lección interactiva -------------------------

export interface LessonContent {
  intro: string
  ideas: { idea: string; application: string }[]
  takeaways: string[]
  challenges: { title: string; steps: string[]; look_for: string }[]
}

export interface LessonInput {
  id: string
  title: string
  description: string
  json_schema: Record<string, unknown>
  data: Record<string, unknown>
  custom: boolean
}

export interface FieldError {
  loc: string
  msg: string
}

export type Tone = 'info' | 'good' | 'warning' | 'bad'

export type Block =
  | { type: 'kpis'; items: { label: string; value: string; detail: string | null; tone: Tone | null }[] }
  | { type: 'callout'; tone: Tone; title: string; text: string }
  | {
      type: 'table'
      title: string
      description: string | null
      columns: { key: string; label: string; align: 'left' | 'right' }[]
      rows: Record<string, string>[]
    }
  | {
      type: 'line_chart'
      title: string
      subtitle: string | null
      x_label: string
      y_label: string
      series: { name: string; points: [number, number][]; emphasis: boolean }[]
      markers: { series: string; x: number; y: number; label: string }[]
      reference_y: number | null
    }
  | {
      type: 'bar_list'
      title: string
      subtitle: string | null
      min_value: number
      max_value: number
      legend: string | null
      items: { label: string; value: number; display: string; target: number | null; ok: boolean | null; detail: string | null }[]
    }
  | {
      type: 'matrix'
      title: string
      subtitle: string | null
      x_label: string
      y_label: string
      x_range: [number, number]
      y_range: [number, number]
      ticks: number[]
      divider_x: number | null
      divider_y: number | null
      quadrants: { x: number; y: number; text: string }[]
      groups: { id: string; label: string; tone: Tone }[]
      points: { x: number; y: number; label: string; group: string; detail: string | null }[]
    }
  | {
      type: 'heatmap'
      title: string
      subtitle: string | null
      columns: string[]
      rows: { label: string; values: (number | null)[] }[]
      min_value: number
      max_value: number
    }
  | {
      type: 'timeline'
      title: string
      subtitle: string | null
      today: string | null
      groups: { id: string; label: string; tone: Tone }[]
      items: { label: string; group: string; start: string; end: string; note: string | null }[]
    }
  | { type: 'document'; title: string; filename: string; markdown: string }

export interface LessonResult {
  lesson: number
  ran_at: string
  sections: { title: string; blocks: Block[] }[]
}

export interface WorkspaceStatus {
  built: boolean
  built_at: string | null
  built_with: Record<string, unknown> | null
  settings: Record<string, unknown>
  pending_changes: boolean
  tables: { table: string; layer: string; rows: number }[]
  seeded_defects: Record<string, number>
}

export interface WorkspaceOut {
  status: WorkspaceStatus
  json_schema: Record<string, unknown>
}

/** Error de la API con el detalle de validación de pydantic (422) cuando lo hay. */
export class ApiError extends Error {
  status: number
  fields: FieldError[]
  constructor(status: number, message: string, fields: FieldError[] = []) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

export const KIND_LABEL: Record<LessonKind, string> = {
  gestion: 'Gestión',
  tecnico: 'Técnico',
  caso: 'Caso de estudio',
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    if (Array.isArray(detail)) throw new ApiError(res.status, 'Hay campos no válidos', detail)
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  catalog: () => request<CatalogOut>('/lessons'),
  lesson: (n: number) => request<LessonOut>(`/lessons/${n}`),
  setCompleted: (n: number, completed: boolean) =>
    request<LessonState[]>(`/progress/${n}`, {
      method: 'PUT',
      body: JSON.stringify({ completed }),
    }),
  resetProgress: () => request<LessonState[]>('/progress', { method: 'DELETE' }),
  content: (n: number) => request<LessonContent>(`/lessons/${n}/content`),
  inputs: (n: number) => request<LessonInput[]>(`/lessons/${n}/inputs`),
  saveInput: (n: number, id: string, data: unknown) =>
    request<LessonInput>(`/lessons/${n}/inputs/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ data }),
    }),
  resetInput: (n: number, id: string) =>
    request<LessonInput>(`/lessons/${n}/inputs/${id}`, { method: 'DELETE' }),
  run: (n: number) => request<LessonResult>(`/lessons/${n}/run`, { method: 'POST' }),
  result: (n: number) => request<LessonResult | null>(`/lessons/${n}/result`),
  workspace: () => request<WorkspaceOut>('/workspace'),
  saveWorkspaceSettings: (data: unknown) =>
    request<WorkspaceOut>('/workspace/settings', { method: 'PUT', body: JSON.stringify({ data }) }),
  resetWorkspaceSettings: () => request<WorkspaceOut>('/workspace/settings', { method: 'DELETE' }),
  buildWorkspace: () => request<WorkspaceOut>('/workspace/build', { method: 'POST' }),
  resetWorkspace: () => request<WorkspaceOut>('/workspace', { method: 'DELETE' }),
}
