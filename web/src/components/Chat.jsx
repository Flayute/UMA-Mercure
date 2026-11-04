import { useState } from 'react'

export default function Chat() {
  const [message, setMessage] = useState('')
  const [response, setResponse] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSend(e) {
    e.preventDefault()
    if (!message.trim() || loading) return

    setLoading(true)
    setResponse(null)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message.trim() })
      })
      const data = await res.json()
      setResponse(data)
      setMessage('')
      
      // Emitir evento para el ResponseViewer
      const event = new CustomEvent('uma-ai-response', { detail: data.message })
      window.dispatchEvent(event)
    } catch (err) {
      setResponse({ message: 'Error conectando con el cerebro. ¿Está llama-server activo?' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <h2>DJ Inteligente</h2>
      </div>

      <form onSubmit={handleSend}>
        <div className="chat-input-wrapper">
          <input
            className="chat-input"
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Pon algo de Gramatik..."
            disabled={loading}
          />
          <button
            className="chat-send-btn"
            type="submit"
            disabled={loading || !message.trim()}
          >
            {loading ? 'Enviando…' : 'Enviar'}
          </button>
        </div>
      </form>

      {response && (
        <div className="chat-response">
          {response.message}
        </div>
      )}
    </div>
  )
}
