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
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
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
}
