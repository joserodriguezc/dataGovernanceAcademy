import { useState } from 'react'
import Markdown from 'react-markdown'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import remarkGfm from 'remark-gfm'
import type { Block, LessonResult } from '../api.ts'
import { Heatmap, MatrixChart, Timeline } from './Charts.tsx'

// Colores categóricos en orden fijo (nunca reciclados); el modo oscuro tiene sus propios tonos.
const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']
const number = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 })

function ChartBlock({ block }: { block: Extract<Block, { type: 'line_chart' }> }) {
  const xs = [...new Set(block.series.flatMap((s) => s.points.map(([x]) => x)))].sort((a, b) => a - b)
  const rows = xs.map((x) => {
    const row: Record<string, number> = { x }
    for (const s of block.series) {
      const point = s.points.find(([px]) => px === x)
      if (point) row[s.name] = point[1]
    }
    return row
  })
  const color = (name: string) =>
    SERIES[block.series.findIndex((s) => s.name === name) % SERIES.length]

  return (
    <figure className="chart">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickLine={false}
                 stroke="var(--axis)" tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                 label={{ value: block.x_label, position: 'insideBottom', offset: -12,
                          fill: 'var(--text-muted)', fontSize: 12 }} />
          <YAxis tickLine={false} stroke="var(--axis)" width={56}
                 tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                 tickFormatter={(v: number) => number.format(v)}
                 label={{ value: block.y_label, angle: -90, position: 'insideLeft',
                          fill: 'var(--text-muted)', fontSize: 12, dy: 60 }} />
          <Tooltip
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)',
                            borderRadius: 8, color: 'var(--text)' }}
            labelFormatter={(x) => `${block.x_label} ${x}`}
            formatter={(v) => number.format(Number(v))} />
          <Legend verticalAlign="top" height={32} wrapperStyle={{ color: 'var(--text-muted)' }} />
          {block.reference_y !== null && (
            <ReferenceLine y={block.reference_y} stroke="var(--axis)" />
          )}
          {block.series.map((s) => (
            <Line key={s.name} type="monotone" dataKey={s.name} stroke={color(s.name)}
                  strokeWidth={s.emphasis ? 3 : 2} dot={false} activeDot={{ r: 5 }}
                  isAnimationActive={false} />
          ))}
          {block.markers.map((m) => (
            <ReferenceDot key={m.label} x={m.x} y={m.y} r={6} fill={color(m.series)}
                          stroke="var(--surface)" strokeWidth={2} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {block.markers.length > 0 && (
        <ul className="chart-notes">
          {block.markers.map((m) => (
            <li key={m.label}><span className="swatch" style={{ background: color(m.series) }} />{m.label}</li>
          ))}
        </ul>
      )}
    </figure>
  )
}

function DocumentView({ block }: { block: Extract<Block, { type: 'document' }> }) {
  const [open, setOpen] = useState(false)
  function download() {
    const url = URL.createObjectURL(new Blob([block.markdown], { type: 'text/markdown' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: block.filename })
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="document">
      <div className="document-head">
        <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? '▾' : '▸'} {block.title}
        </button>
        <button className="button small" onClick={download}>Descargar .md</button>
      </div>
      {open && (
        <div className="markdown">
          <Markdown remarkPlugins={[remarkGfm]}>{block.markdown}</Markdown>
        </div>
      )}
    </div>
  )
}

function BarList({ block }: { block: Extract<Block, { type: 'bar_list' }> }) {
  const span = block.max_value - block.min_value || 1
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - block.min_value) / span) * 100))}%`
  return (
    <figure className="bar-list">
      <figcaption>
        <strong>{block.title}</strong>
        {block.subtitle && <span className="muted">{block.subtitle}</span>}
      </figcaption>
      <ul>
        {block.items.map((item) => (
          <li key={item.label} title={item.detail ?? undefined}>
            <span className="bar-label">{item.label}</span>
            <span className="bar-track">
              <span className={`bar-fill${item.ok === false ? ' bad' : item.ok ? ' good' : ''}`}
                    style={{ width: pos(item.value) }} />
              {item.target !== null && <span className="bar-target" style={{ left: pos(item.target) }} />}
            </span>
            <span className="bar-value">
              {item.display}
              {item.ok !== null && <span className={item.ok ? 'ok' : 'ko'}>{item.ok ? ' ✓' : ' ✗'}</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="muted bar-legend">
        {block.legend ?? `Escala de ${Math.round(block.min_value * 100)} % a ${Math.round(block.max_value * 100)} % · la marca vertical es el umbral · ✓ cumple · ✗ no cumple`}
      </p>
    </figure>
  )
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case 'kpis':
      return (
        <div className="kpis">
          {block.items.map((k) => (
            <div key={k.label} className={`kpi${k.tone ? ` tone-${k.tone}` : ''}`}>
              <span className="kpi-label">{k.label}</span>
              <span className="kpi-value">{k.value}</span>
              {k.detail && <span className="muted kpi-detail">{k.detail}</span>}
            </div>
          ))}
        </div>
      )
    case 'callout':
      return (
        <div className={`callout tone-${block.tone}`}>
          <strong>{block.title}</strong>
          <p>{block.text}</p>
        </div>
      )
    case 'table':
      return (
        <div className="table-block">
          <h4>{block.title}</h4>
          {block.description && <p className="muted">{block.description}</p>}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>{block.columns.map((c) => <th key={c.key} className={c.align}>{c.label}</th>)}</tr>
              </thead>
              <tbody>
                {block.rows.map((row, i) => (
                  <tr key={i}>
                    {block.columns.map((c) => <td key={c.key} className={c.align}>{row[c.key]}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )
    case 'line_chart':
      return <ChartBlock block={block} />
    case 'bar_list':
      return <BarList block={block} />
    case 'matrix':
      return <MatrixChart block={block} />
    case 'heatmap':
      return <Heatmap block={block} />
    case 'timeline':
      return <Timeline block={block} />
    case 'document':
      return <DocumentView block={block} />
  }
}

export default function ResultView({ result }: { result: LessonResult }) {
  return (
    <div className="result">
      {result.sections.map((section) => (
        <section key={section.title} className="result-section">
          <h3>{section.title}</h3>
          {section.blocks.map((block, i) => <BlockView key={i} block={block} />)}
        </section>
      ))}
    </div>
  )
}
