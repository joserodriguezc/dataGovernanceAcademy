import type { Block, Tone } from '../api.ts'

// Bloques dibujados con SVG/HTML propio: matriz de cuadrantes, mapa de calor y línea de tiempo.
// La identidad nunca va solo en el color: la matriz usa forma y las barras llevan texto.

const TONE_COLOR: Record<Tone, string> = {
  good: 'var(--good)', info: 'var(--series-1)', bad: 'var(--bad)', warning: 'var(--series-4)',
}
const SERIES_BY_TONE: Record<Tone, string> = {
  info: 'var(--series-1)', warning: 'var(--series-2)', good: 'var(--series-3)', bad: 'var(--series-4)',
}

function Shape({ tone, x, y, r = 7 }: { tone: Tone; x: number; y: number; r?: number }) {
  const common = { fill: TONE_COLOR[tone], stroke: 'var(--surface)', strokeWidth: 2 }
  if (tone === 'bad') {
    return <polygon points={`${x},${y - r} ${x + r},${y + r * 0.8} ${x - r},${y + r * 0.8}`} {...common} />
  }
  if (tone === 'info') return <rect x={x - r * 0.85} y={y - r * 0.85} width={r * 1.7} height={r * 1.7} {...common} />
  if (tone === 'warning') return <polygon points={`${x},${y - r} ${x + r},${y} ${x},${y + r} ${x - r},${y}`} {...common} />
  return <circle cx={x} cy={y} r={r} {...common} />
}

export function MatrixChart({ block }: { block: Extract<Block, { type: 'matrix' }> }) {
  const W = 760, H = 520, M = { l: 56, r: 150, t: 16, b: 48 }
  const [x0, x1] = block.x_range, [y0, y1] = block.y_range
  const sx = (v: number) => M.l + ((v - x0) / (x1 - x0)) * (W - M.l - M.r)
  const sy = (v: number) => H - M.b - ((v - y0) / (y1 - y0)) * (H - M.t - M.b)
  const tone = Object.fromEntries(block.groups.map((g) => [g.id, g.tone]))
  return (
    <figure className="chart svg-chart">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={block.title}>
        <rect x={M.l} y={M.t} width={W - M.l - M.r} height={H - M.t - M.b} fill="none" stroke="var(--grid)" />
        {block.ticks.map((t) => (
          <g key={t}>
            <text x={sx(t)} y={H - M.b + 18} textAnchor="middle" className="tick">{t}</text>
            <text x={M.l - 10} y={sy(t) + 4} textAnchor="end" className="tick">{t}</text>
          </g>
        ))}
        {block.divider_x !== null && (
          <line x1={sx(block.divider_x)} x2={sx(block.divider_x)} y1={M.t} y2={H - M.b} stroke="var(--axis)" />
        )}
        {block.divider_y !== null && (
          <line x1={M.l} x2={W - M.r} y1={sy(block.divider_y)} y2={sy(block.divider_y)} stroke="var(--axis)" />
        )}
        {block.quadrants.map((q) => (
          <text key={q.text} x={sx(q.x)} y={sy(q.y)} className="quadrant">{q.text}</text>
        ))}
        <text x={(M.l + W - M.r) / 2} y={H - 8} textAnchor="middle" className="axis-label">{block.x_label}</text>
        <text transform={`translate(16 ${(M.t + H - M.b) / 2}) rotate(-90)`} textAnchor="middle" className="axis-label">{block.y_label}</text>
        {block.points.map((p) => (
          <g key={p.label + p.x + p.y}>
            <title>{p.detail ?? p.label}</title>
            <Shape tone={tone[p.group] ?? 'info'} x={sx(p.x)} y={sy(p.y)} />
            <text x={sx(p.x) + 11} y={sy(p.y) + 4} className="point-label">{p.label}</text>
          </g>
        ))}
      </svg>
      <ul className="chart-notes">
        {block.groups.map((g) => (
          <li key={g.id}>
            <svg width="16" height="16" aria-hidden="true"><Shape tone={g.tone} x={8} y={8} r={6} /></svg> {g.label}
          </li>
        ))}
      </ul>
    </figure>
  )
}

export function Heatmap({ block }: { block: Extract<Block, { type: 'heatmap' }> }) {
  const span = block.max_value - block.min_value || 1
  const fmt = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 })
  return (
    <figure className="chart heatmap">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <div className="table-scroll">
        <table>
          <thead>
            <tr><th />{block.columns.map((c) => <th key={c} className="heat-col">{c}</th>)}</tr>
          </thead>
          <tbody>
            {block.rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                {row.values.map((v, i) => {
                  if (v === null) return <td key={i} className="heat-cell empty">—</td>
                  const t = (v - block.min_value) / span
                  return (
                    <td key={i} className={`heat-cell${t > 0.55 ? ' dark' : ''}`}
                        style={{ background: `color-mix(in srgb, var(--series-1) ${Math.round(12 + t * 88)}%, var(--bg))` }}>
                      {fmt.format(v)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}

export function Timeline({ block }: { block: Extract<Block, { type: 'timeline' }> }) {
  const day = (s: string) => new Date(s + 'T00:00:00').getTime()
  const starts = block.items.map((i) => day(i.start))
  const ends = block.items.map((i) => day(i.end))
  const min = Math.min(...starts, block.today ? day(block.today) : Infinity)
  const max = Math.max(...ends, block.today ? day(block.today) : -Infinity)
  const pos = (t: number) => `${((t - min) / (max - min || 1)) * 100}%`
  const tone = Object.fromEntries(block.groups.map((g) => [g.id, g.tone]))
  const fmt = (s: string) => new Date(s + 'T00:00:00').toLocaleDateString('es-ES', { month: 'short', year: 'numeric' })
  return (
    <figure className="chart timeline">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <ul className="chart-notes">
        {block.groups.map((g) => (
          <li key={g.id}><span className="swatch" style={{ background: SERIES_BY_TONE[g.tone] }} />{g.label}</li>
        ))}
      </ul>
      <div className="tl-rows">
        {block.today && (
          <div className="tl-row tl-head">
            <span />
            <span className="tl-track bare">
              <span className="tl-today-label" style={{ left: pos(day(block.today)) }}>
                Corte {new Date(block.today + 'T00:00:00').toLocaleDateString('es-ES')}
              </span>
            </span>
          </div>
        )}
        {block.items.map((item) => (
          <div key={item.label} className="tl-row" title={`${item.label}: ${fmt(item.start)} → ${fmt(item.end)}`}>
            <span className="tl-label">{item.label}</span>
            <span className="tl-track">
              <span className="tl-bar" style={{
                left: pos(day(item.start)),
                width: `max(4px, calc(${pos(day(item.end))} - ${pos(day(item.start))}))`,
                background: SERIES_BY_TONE[tone[item.group] ?? 'info'],
              }} />
              {item.note && <span className="tl-note" style={{ left: pos(day(item.end)) }}>{item.note}</span>}
              {block.today && <span className="tl-today" style={{ left: pos(day(block.today)) }} />}
            </span>
          </div>
        ))}
      </div>
      <div className="tl-axis"><span>{fmt(new Date(min).toISOString().slice(0, 10))}</span><span>{fmt(new Date(max).toISOString().slice(0, 10))}</span></div>
    </figure>
  )
}
