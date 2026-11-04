import { useState, useEffect } from 'react'

export default function Stats() {
  const [stats, setStats] = useState(null)
  const [db, setDb] = useState(null)

  useEffect(() => {
    fetch('/api/music/stats')
      .then(res => res.json())
      .then(setStats)
      .catch(() => {})
    fetch('/api/music/db/stats')
      .then(res => res.json())
      .then(setDb)
      .catch(() => {})
  }, [])

  if (!stats && !db) return null

  const totalMinutes = Math.floor(parseFloat(stats?.db_playtime || 0) / 60)

  return (
    <div className="card">
      <div className="card-header">
        <h2>Estadísticas</h2>
      </div>

      <div className="stats-grid">
        <div className="stat-item">
          <div className="value">{(db?.total || 0).toLocaleString('es-ES')}</div>
          <div className="label">Temas en catálogo</div>
        </div>
        <div className="stat-item">
          <div className="value">{db?.never_played ?? '-'}</div>
          <div className="label">Nunca reproducidos</div>
        </div>
        <div className="stat-item">
          <div className="value">{db?.avg_bpm ?? '-'}</div>
          <div className="label">BPM medio</div>
        </div>
        <div className="stat-item">
          <div className="value">{totalMinutes}</div>
          <div className="label">Min. indexados</div>
        </div>
      </div>

      {db?.top_artists?.length > 0 && (
        <div style={{ marginTop: '10px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Top artistas: {db.top_artists.map(a => `${a.artist} (${a.plays})`).join(' · ')}
        </div>
      )}
    </div>
  )
}
