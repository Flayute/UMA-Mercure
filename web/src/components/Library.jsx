import { useState, useEffect } from 'react'
import { apiUrl } from '../hooks/useSid'

export default function Library() {
  const [data, setData] = useState(null)

  useEffect(() => {
    const load = () => fetch(apiUrl('/api/session/queue')).then(res => res.json()).then(setData).catch(() => {})
    load()
    const interval = setInterval(load, 3000)
    return () => clearInterval(interval)
  }, [])

  async function jump(index) {
    try {
      await fetch(apiUrl('/api/session/play_index'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index })
      })
    } catch (e) {
      console.error('Error jumping track:', e)
    }
  }

  const items = data?.items || []

  return (
    <div className="card">
      <div className="card-header">
        <h2>Cola de Reproducción ({items.length})</h2>
      </div>

      <div className="library-list" style={{ maxHeight: '420px', overflowY: 'auto' }}>
        {items.map((it) => (
          <div
            key={it.index}
            className={`library-item ${it.index === data?.current_index ? 'active' : ''}`}
            onClick={() => jump(it.index)}
          >
            <span className="num">{it.index + 1}</span>
            <div className="meta">
              <div className="name">{it.title || it.file.split('/').pop()}</div>
              <div className="sub">{it.artist || 'Desconocido'}</div>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Cola vacía — usa "Radio completa" o "A la cola" del buscador.
          </p>
        )}
      </div>
    </div>
  )
}
