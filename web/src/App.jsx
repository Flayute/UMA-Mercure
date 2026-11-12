import './index.css'
import { useState, useEffect } from 'react'
import { usePlayerStatus } from './hooks/usePlayerStatus'
import { getSid, setSid, apiUrl } from './hooks/useSid'
import Player from './components/Player'
import Chat from './components/Chat'
import Library from './components/Library'
import Catalog from './components/Catalog'
import Stats from './components/Stats'
import SmartPlaylistForm from './components/SmartPlaylistForm'
import ResponseViewer from './components/ResponseViewer'

function HddBanner() {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    const load = () => fetch('/api/music/library/count').then(r => r.json()).then(setInfo).catch(() => {})
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])
  if (!info) return null
  const style = {
    padding: '8px 14px', marginBottom: '12px', borderRadius: '10px', fontSize: '0.85rem',
    background: info.hdd_present ? 'rgba(80,200,120,0.12)' : 'rgba(230,180,60,0.12)',
    color: info.hdd_present ? '#7ed493' : '#e3b955',
  }
  return (
    <div style={style}>
      {info.hdd_present
        ? `HDD conectado — fonoteca disponible para reproducción (${info.total.toLocaleString('es-ES')} temas)`
        : `HDD desconectado — catálogo de ${info.total.toLocaleString('es-ES')} temas visible, reproducción en pausa hasta conectar el Seagate`}
    </div>
  )
}

function App() {
  const [sid, setSidState] = useState(getSid())
  const { status, current, connected } = usePlayerStatus(sid)
  // Vista por defecto: radio en puro streaming. La interfaz completa se abre
  // solo cuando el visitante pide una sesión individual.
  const [expanded, setExpanded] = useState(false)

  const handleSid = (s) => {
    setSid(s); setSidState(s)
    setExpanded(!!s && s !== 'main')
  }

  // Radio principal = aleatorio de toda la fonoteca: si la sesión 'main' está
  // vacía (primer arranque o cola borrada) se carga barajada.
  useEffect(() => {
    if (sid !== 'main') return
    fetch(apiUrl('/api/session')).then(r => r.json()).then(s => {
      if (s && (!s.queue_len || (s.state === 'stop' && !s.file))) {
        fetch(apiUrl('/api/session/shuffle_all'), { method: 'POST' }).catch(() => {})
      }
    }).catch(() => {})
  }, [sid])

  async function openSession() {
    try {
      const r = await fetch('/api/session/fork?sid=' + encodeURIComponent(getSid()), { method: 'POST' })
      const data = await r.json()
      if (data.sid) handleSid(data.sid)
      else setExpanded(true)
    } catch (_) {
      setExpanded(true)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>UMA Mercure</h1>
        <div className="status-badge">
          <span className={`status-dot ${connected ? '' : 'offline'}`} />
          {connected ? 'Conectado' : 'Desconectado'}
        </div>
      </header>

      <HddBanner />

      <Player status={status} current={current} connected={connected} sid={sid} onSid={handleSid} />

      {!expanded ? (
        <div style={{ textAlign: 'center', marginTop: 18 }}>
          <button
            onClick={openSession}
            title="Crea una sesión de reproducción solo para este dispositivo y abre la interfaz completa: búsqueda, catálogo, listas inteligentes y chat"
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--accent)',
              color: 'var(--text-primary)', borderRadius: 100, padding: '12px 26px',
              fontSize: '0.95rem', cursor: 'pointer',
            }}
          >
            Sesión individual →
          </button>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 10 }}>
            La radio suena para todo el mundo; si personalizas, solo cambia en tu dispositivo.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', margin: '6px 0 12px' }}>
            <button
              onClick={() => handleSid('main')}
              title="Cierra la interfaz completa, abandona la sesión paralela y vuelve al streaming común de la radio"
              style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', borderRadius: 100, padding: '6px 14px',
                fontSize: '0.75rem', cursor: 'pointer',
              }}
            >
              ← Volver a la vista radio
            </button>
          </div>

          <div className="main-grid">
            <div className="side-panel">
              <Chat />
              <SmartPlaylistForm />
              <Stats />
            </div>
            <ResponseViewer />
          </div>

          <Catalog currentFile={current?.file} />

          <Library currentFile={current?.file} />
        </>
      )}
    </div>
  )
}

export default App
