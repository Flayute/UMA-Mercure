import { useState, useEffect, useCallback } from 'react'
import { apiUrl } from '../hooks/useSid'

const badgeStyle = {
  display: 'inline-block', fontSize: '0.65rem', padding: '1px 6px',
  borderRadius: '6px', background: 'rgba(255,255,255,0.08)',
  color: 'var(--text-muted)', marginRight: '4px',
}

export default function Catalog({ currentFile }) {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const PAGE = 100

  const fetchPage = useCallback((from, query) => {
    setLoading(true)
    const url = `/api/music/library?limit=${PAGE}&offset=${from}` + (query ? `&q=${encodeURIComponent(query)}` : '')
    fetch(url)
      .then(res => res.json())
      .then(data => {
        setRows(prev => from === 0 ? data : [...prev, ...data])
        setOffset(from)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetch('/api/music/library/count').then(res => res.json()).then(d => setTotal(d.total)).catch(() => {})
    fetchPage(0, '')
  }, [fetchPage])

  function search(e) {
    e.preventDefault()
    fetchPage(0, q)
  }

  async function playTrack(row) {
    try {
      await fetch(apiUrl('/api/session/play_file'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: row.file })
      })
    } catch (e) {
      console.error('Error playing track:', e)
    }
  }

  async function addToQueue(e, row) {
    e.stopPropagation()
    try {
      await fetch(apiUrl('/api/session/add_files'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: [row.file] })
      })
    } catch (e) {
      console.error('Error adding to queue:', e)
    }
  }

  async function radioMode() {
    try {
      await fetch(apiUrl('/api/session/shuffle_all'), { method: 'POST' })
    } catch (e) {
      console.error('Error starting radio mode:', e)
    }
  }

  async function queueAll() {
    try {
      const res = await fetch(apiUrl('/api/session/add_files'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: rows.map(r => r.file) })
      })
      const data = await res.json()
      window.dispatchEvent(new CustomEvent('uma-ai-response', {
        detail: `${data.added} pistas añadidas a la cola (total: ${data.queue_len}).`
      }))
    } catch (e) {
      console.error('Error queueing results:', e)
    }
  }

  return (
    <div className="card">
      <div className="card-header" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h2>Catálogo ({total.toLocaleString('es-ES')})</h2>
        </div>
        <button className="btn" onClick={radioMode} title="Pone toda la biblioteca en aleatorio y reproduce (modo radio)">
          Radio completa
        </button>
      </div>

      <form onSubmit={search} style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
        <input
          className="catalog-search"
          style={{ flex: 1 }}
          placeholder="Buscar artista, título, género, mood..."
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        <button type="submit" className="btn">Buscar</button>
      </form>

      <div className="library-list" style={{ maxHeight: '420px', overflowY: 'auto' }}>
        {rows.map((row, i) => (
          <div
            key={`${row.file}-${i}`}
            className={`library-item ${currentFile === row.file ? 'active' : ''}`}
            onClick={() => playTrack(row)}
          >
            <div className="meta">
              <div className="name">{row.title || row.file.split('/').pop()}</div>
              <div className="sub">
                {row.artist || 'Desconocido'}
                {row.genre && <span style={badgeStyle}>{row.genre}</span>}
                {row.bpm && <span style={badgeStyle}>{Math.round(row.bpm)} BPM</span>}
                {row.mood && <span style={badgeStyle}>{row.mood}</span>}
                {row.play_count > 0 && <span style={badgeStyle}>▶ {row.play_count}</span>}
              </div>
            </div>
            <button
              className="btn"
              style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: '0.75rem' }}
              title="Añadir a la cola sin cortar la reproducción"
              onClick={(e) => addToQueue(e, row)}
            >
              + cola
            </button>
          </div>
        ))}
        {rows.length === 0 && !loading && (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Nada en el catálogo con esa búsqueda.</p>
        )}
      </div>

      <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
        {rows.length < total && (
          <button className="btn" onClick={() => fetchPage(offset + PAGE, q)}>
            {loading ? 'Cargando...' : `Cargar más (${rows.length}/${total.toLocaleString('es-ES')})`}
          </button>
        )}
        <button className="btn" onClick={queueAll} disabled={rows.length === 0}
          title="Añade todas las pistas cargadas aquí a la cola de reproducción">
          A la cola ({rows.length})
        </button>
      </div>
    </div>
  )
}
