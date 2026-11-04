import './index.css'
import { useState, useEffect } from 'react'
import { usePlayerStatus } from './hooks/usePlayerStatus'
import { getSid, setSid } from './hooks/useSid'
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
  const handleSid = (s) => { setSid(s); setSidState(s) }

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
    </div>
  )
}

export default App
