import { useRef, useEffect, useState } from 'react'
import { apiUrl, getSid } from '../hooks/useSid'

function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00'
  const s = Math.floor(parseFloat(seconds))
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function Player({ status, current, connected, sid = 'main', onSid }) {
  const audioRef = useRef(null)
  const isPlaying = status?.state === 'play'
  const position = parseFloat(status?.elapsed || 0)
  const duration = parseFloat(current?.duration || current?.time || 0)
  const progress = duration > 0 ? (position / duration) * 100 : 0

  const title = current?.title || 'Sin reproducción'
  const artist = current?.artist || '—'
  const [vol, setVol] = useState(() => Number(localStorage.getItem('uma-volume') ?? '0.8'))

  // La pista actual se carga como archivo directo (HTTP Range → seek instantáneo)
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const file = current?.file
    if (!file) {
      el.pause()
      el.removeAttribute('src')
      el.dataset.track = ''
      return
    }
    if (el.dataset.track !== file) {
      el.dataset.track = file
      el.src = `/api/music/stream?file=${encodeURIComponent(file)}`
      el.load()
      if ('mediaSession' in navigator && typeof MediaMetadata !== 'undefined') {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: current?.title || file.split('/').pop(),
          artist: current?.artist || 'UMA Mercure'
        })
      }
    }
    if (isPlaying) el.play().catch(() => {})
  }, [current?.file])

  // Sincronizar play/pause y corregir deriva contra el reloj del servidor.
  // Ojo: hacer play() sobre un <audio> en estado 'ended' REINICIA la pista —
  // por eso el guard de ended.
  useEffect(() => {
    const el = audioRef.current
    if (!el || !el.src) return
    if (isPlaying) {
      if (!el.ended) {
        el.play().catch(() => {})
        if (Math.abs(el.currentTime - position) > 1.5) el.currentTime = position
      }
    } else {
      el.pause()
    }
  }, [isPlaying, position])

  // La pista terminó en el navegador antes que el reloj del servidor (duration
  // fallback o deriva): pide el salto. Si el servidor ya ve la pista terminada,
  // NO pide nada — el ticker avanza y evita el doble salto.
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const onEnded = async () => {
      try {
        const snap = await (await fetch(apiUrl('/api/session'))).json()
        if (snap.state === 'play' && snap.position < snap.duration - 1) {
          await fetch(apiUrl('/api/session/next'), { method: 'POST' })
        }
      } catch (_) {}
    }
    el.addEventListener('ended', onEnded)
    return () => el.removeEventListener('ended', onEnded)
  }, [])

  // MediaSession: notificación Android (Firefox) + controles de transporte
  useEffect(() => {
    if (!('mediaSession' in navigator)) return
    const act = (a) => fetch(`/api/session/${a}`, { method: 'POST' }).catch(() => {})
    navigator.mediaSession.setActionHandler('play', () => act('play'))
    navigator.mediaSession.setActionHandler('pause', () => act('pause'))
    navigator.mediaSession.setActionHandler('nexttrack', () => act('next'))
    navigator.mediaSession.setActionHandler('previoustrack', () => act('previous'))
    navigator.mediaSession.setActionHandler('seekto', (d) => {
      if (d.seekTime != null) {
        fetch('/api/session/seek', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seconds: d.seekTime })
        }).catch(() => {})
      }
    })
  }, [])

  // Volumen LOCAL por dispositivo (no global como MPD)
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = vol
    localStorage.setItem('uma-volume', String(vol))
  }, [vol])

  // Archivo ilegible en este navegador (codec raro, fichero corrupto): saltar
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const onError = () => {
      if (el.dataset.track && el.dataset.track !== el.dataset.skipped) {
        el.dataset.skipped = el.dataset.track
        fetch('/api/session/next', { method: 'POST' }).catch(() => {})
      }
    }
    el.addEventListener('error', onError)
    return () => el.removeEventListener('error', onError)
  }, [])

  // El navegador bloquea el autoplay hasta el primer gesto del usuario
  useEffect(() => {
    const unlock = () => {
      const el = audioRef.current
      if (el && isPlaying && el.src) el.play().catch(() => {})
    }
    window.addEventListener('pointerdown', unlock)
    return () => window.removeEventListener('pointerdown', unlock)
  }, [isPlaying])

  async function sendControl(action) {
    try {
      await fetch(apiUrl(`/api/session/${action}`), { method: 'POST' })
    } catch (e) {
      console.error('Control error:', e)
    }
  }

  // Bifurcar: nueva sesión que copia cola y posición; desde ese momento este
  // dispositivo es independiente (los demás siguen en 'main').
  async function fork() {
    try {
      const r = await fetch('/api/session/fork?sid=' + encodeURIComponent(getSid()), { method: 'POST' })
      const data = await r.json()
      if (data.sid) onSid?.(data.sid)
    } catch (_) {}
  }

  async function seekTo(e) {
    if (duration <= 0) return
    const bar = e.currentTarget.getBoundingClientRect()
    const sec = ((e.clientX - bar.left) / bar.width) * duration
    try {
      await fetch(apiUrl('/api/session/seek'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seconds: sec })
      })
      if (audioRef.current) audioRef.current.currentTime = sec
    } catch (_) {}
  }

  return (
    <div className="card player-card">
      <audio ref={audioRef} />

      <div className="card-header" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2>Reproductor</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {sid !== 'main' ? (
            <>
              <span className="status-badge" style={{ borderColor: 'var(--accent)' }}>Sesión propia</span>
              <button className="ctrl-btn" style={{ fontSize: '0.72rem', padding: '6px 10px' }} onClick={() => onSid?.('main')} title="Abandona la sesión paralela y vuelve a la reproducción compartida">Volver a la radio común</button>
            </>
          ) : (
            <button className="ctrl-btn" style={{ fontSize: '0.72rem', padding: '6px 10px' }} onClick={fork} title="Crea una reproducción independiente para este dispositivo: copia la cola actual y a partir de ahí nadie te cambia la música">Crear sesión propia</button>
          )}
          <div className="status-badge">
            <span className={`status-dot ${isPlaying ? '' : 'offline'}`} />
            {isPlaying ? 'Sonando' : 'En pausa'}
          </div>
        </div>
      </div>

      <div className="now-playing">
        <div className={`album-art ${isPlaying ? 'playing' : ''}`}>
          ♪
        </div>
        <div className="track-info">
          <div className="title">{title}</div>
          <div className="artist">{artist}</div>
          <div className="progress-bar" onClick={seekTo} title="Clic para buscar en la pista" style={{ cursor: 'pointer' }}>
            <div className="fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="time-display">
            <span>{formatTime(position)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>
      </div>

      <div className="controls">
        <button className="ctrl-btn" onClick={() => sendControl('previous')} title="Anterior">
          ⏮
        </button>
        <button className="ctrl-btn primary" onClick={() => sendControl(isPlaying ? 'pause' : 'play')} title={isPlaying ? 'Pausar' : 'Reproducir'}>
          {isPlaying ? '⏸' : '▶'}
        </button>
        <button className="ctrl-btn" onClick={() => sendControl('next')} title="Siguiente">
          ⏭
        </button>
        <button className="ctrl-btn" onClick={() => sendControl('stop')} title="Detener">
          ⏹
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '10px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Volumen</span>
        <input
          type="range" min="0" max="100" value={Math.round(vol * 100)}
          style={{ flex: 1 }}
          onChange={e => setVol(Number(e.target.value) / 100)}
        />
      </div>
    </div>
  )
}
