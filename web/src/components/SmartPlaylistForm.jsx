import { useState } from 'react'

export default function SmartPlaylistForm() {
  const [params, setParams] = useState({
    limit: 20,
    bpm: '',
    genre: '',
    mood: ''
  })
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: `FORM_ACTION:smart_playlist`,
          direct_params: {
            action: "smart_playlist",
            params: {
              genre: params.genre,
              bpm: params.bpm ? parseInt(params.bpm) : null,
              mood: params.mood
            },
            limit: parseInt(params.limit)
          }
        })
      })
      const data = await res.json()
      const msg = data.message || 'Playlist generada.'
      // Mostrar el resultado en el Visor de Razonamiento, igual que el Chat
      window.dispatchEvent(new CustomEvent('uma-ai-response', { detail: msg }))
    } catch (err) {
      console.error('Error generating playlist:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>Generador de Listas</h2>
      </div>
      
      <form onSubmit={handleSubmit} className="smart-form">
        <div className="form-grid">
          <div className="form-group">
            <label>Nº Canciones</label>
            <input 
              type="number" 
              value={params.limit} 
              onChange={(e) => setParams({...params, limit: e.target.value})}
              min="1" max="100"
            />
          </div>
          <div className="form-group">
            <label>BPM Objetivo</label>
            <input 
              type="number" 
              placeholder="Ej: 120"
              value={params.bpm} 
              onChange={(e) => setParams({...params, bpm: e.target.value})}
            />
          </div>
          <div className="form-group">
            <label>Género</label>
            <input 
              type="text" 
              placeholder="Jazz, Rock..."
              value={params.genre} 
              onChange={(e) => setParams({...params, genre: e.target.value})}
            />
          </div>
          <div className="form-group">
            <label>Mood / Energía</label>
            <select 
              value={params.mood} 
              onChange={(e) => setParams({...params, mood: e.target.value})}
            >
              <option value="">Cualquiera</option>
              <option value="Alegre">Alegre</option>
              <option value="Chill">Chill</option>
              <option value="Energético">Energético</option>
              <option value="Oscuro">Oscuro</option>
            </select>
          </div>
        </div>
        
        <button type="submit" className="generate-btn" disabled={loading}>
          {loading ? 'Generando…' : 'Crear playlist'}
        </button>
      </form>
    </div>
  )
}
