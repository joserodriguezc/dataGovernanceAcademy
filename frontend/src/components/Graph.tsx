import { useMemo, useState } from 'react'
import type { Block, Tone } from '../api.ts'

// Grafo dirigido por capas (linaje, flujos de arquitectura). Al elegir un nodo se resalta de
// qué depende (aguas arriba) y qué depende de él (aguas abajo); el resto se atenúa.

type GraphData = Extract<Block, { type: 'graph' }>

const TONE_STROKE: Record<Tone, string> = {
  good: 'var(--good)', info: 'var(--series-1)', bad: 'var(--bad)', warning: 'var(--series-4)',
}
const NODE_W = 170
const NODE_H = 26
const ROW = 34
const COL_GAP = 70
const PAD = 12

function reach(start: string, next: Map<string, string[]>): Set<string> {
  const seen = new Set<string>()
  const stack = [start]
  while (stack.length) {
    for (const n of next.get(stack.pop()!) ?? []) {
      if (!seen.has(n)) {
        seen.add(n)
        stack.push(n)
      }
    }
  }
  return seen
}

function layout(block: GraphData) {
  const parents = new Map<string, string[]>()
  const children = new Map<string, string[]>()
  for (const e of block.edges) {
    children.set(e.source, [...(children.get(e.source) ?? []), e.target])
    parents.set(e.target, [...(parents.get(e.target) ?? []), e.source])
  }
  // Orden dentro de cada capa: el de la capa anterior (media de la posición de los padres),
  // que reduce los cruces; la primera capa, alfabética.
  const order = new Map<string, number>()
  const columns = block.layers.map((layer) => block.nodes.filter((n) => n.layer === layer))
  columns.forEach((nodes, c) => {
    const key = (id: string) => {
      const ps = (parents.get(id) ?? []).filter((p) => order.has(p))
      return ps.length ? ps.reduce((a, p) => a + order.get(p)!, 0) / ps.length : Infinity
    }
    const sorted = c === 0
      ? [...nodes].sort((a, b) => a.label.localeCompare(b.label))
      : [...nodes].sort((a, b) => key(a.id) - key(b.id) || a.label.localeCompare(b.label))
    sorted.forEach((n, i) => order.set(n.id, i))
    columns[c] = sorted
  })
  const tallest = Math.max(1, ...columns.map((c) => c.length))
  const height = PAD * 2 + 20 + tallest * ROW
  const pos = new Map<string, { x: number; y: number }>()
  columns.forEach((nodes, c) => {
    const offset = ((tallest - nodes.length) * ROW) / 2
    nodes.forEach((n, i) => pos.set(n.id, { x: PAD + c * (NODE_W + COL_GAP), y: PAD + 20 + offset + i * ROW }))
  })
  const width = PAD * 2 + block.layers.length * NODE_W + (block.layers.length - 1) * COL_GAP
  return { parents, children, pos, width, height }
}

export function GraphChart({ block }: { block: GraphData }) {
  const { parents, children, pos, width, height } = useMemo(() => layout(block), [block])
  const [selected, setSelected] = useState<string | null>(block.focus)
  const up = useMemo(() => (selected ? reach(selected, parents) : new Set<string>()), [selected, parents])
  const down = useMemo(() => (selected ? reach(selected, children) : new Set<string>()), [selected, children])
  const lit = (id: string) => !selected || id === selected || up.has(id) || down.has(id)
  const byId = new Map(block.nodes.map((n) => [n.id, n]))
  const maxChars = Math.floor((NODE_W - 12) / 6.6)
  const short = (s: string) => (s.length > maxChars ? s.slice(0, maxChars - 1) + '…' : s)
  const current = selected ? byId.get(selected) : null

  return (
    <figure className="chart svg-chart graph">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <div className="graph-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={block.title}>
          {block.layers.map((layer, c) => (
            <text key={layer} x={PAD + c * (NODE_W + COL_GAP) + NODE_W / 2} y={PAD + 8} textAnchor="middle" className="layer-label">{layer}</text>
          ))}
          {block.edges.map((e, i) => {
            const a = pos.get(e.source), b = pos.get(e.target)
            if (!a || !b) return null
            const same = a.x === b.x
            const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2
            const x2 = same ? b.x + NODE_W : b.x, y2 = b.y + NODE_H / 2
            const d = same
              ? `M${x1},${y1} C${x1 + 40},${y1} ${x2 + 40},${y2} ${x2},${y2}`
              : `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`
            const on = lit(e.source) && lit(e.target)
            return (
              <path key={i} d={d} fill="none"
                    stroke={e.tone ? TONE_STROKE[e.tone] : 'var(--axis)'}
                    strokeWidth={selected && on ? 2 : 1.3} strokeDasharray={e.dashed ? '5 4' : undefined}
                    opacity={on ? 0.95 : 0.12}>
                {e.kind && <title>{`${byId.get(e.source)?.label} → ${byId.get(e.target)?.label}: ${e.kind}`}</title>}
              </path>
            )
          })}
          {block.nodes.map((n) => {
            const p = pos.get(n.id)
            if (!p) return null
            const isSel = n.id === selected
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} className="graph-node"
                 opacity={lit(n.id) ? 1 : 0.3} tabIndex={0} role="button"
                 aria-pressed={isSel} aria-label={n.label}
                 onClick={() => setSelected(isSel ? null : n.id)}
                 onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); setSelected(isSel ? null : n.id) } }}>
                <title>{n.detail ? `${n.id}\n${n.detail}` : n.id}</title>
                <rect width={NODE_W} height={NODE_H} rx={6}
                      fill={isSel ? 'var(--accent-soft)' : 'var(--surface)'}
                      stroke={n.tone ? TONE_STROKE[n.tone] : isSel ? 'var(--accent)' : 'var(--border)'}
                      strokeWidth={n.tone || isSel ? 2 : 1} />
                <text x={8} y={NODE_H / 2 + 4} className="node-label">{short(n.label)}</text>
              </g>
            )
          })}
        </svg>
      </div>
      <p className="muted graph-help" aria-live="polite">
        {current
          ? `${current.id}: depende de ${up.size} y alimenta a ${down.size}. Vuelve a hacer clic para ver todo.`
          : 'Haz clic en un nodo (o usa Tab y Enter) para ver de qué depende y qué depende de él.'}
      </p>
    </figure>
  )
}
