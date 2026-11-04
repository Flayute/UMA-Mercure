import { useState, useEffect } from 'react'

export default function ResponseViewer() {
  const [response, setResponse] = useState('')

  useEffect(() => {
    // Escuchar eventos de nuevas respuestas de la IA
    const handleNewResponse = (e) => {
      setResponse(e.detail)
    }
    window.addEventListener('uma-ai-response', handleNewResponse)
    return () => window.removeEventListener('uma-ai-response', handleNewResponse)
  }, [])

  if (!response) return (
    <div className="card response-viewer empty">
      <div className="card-header">
        <h2>Visor de Razonamiento</h2>
      </div>
      <p className="placeholder">Esperando consultas musicales...</p>
    </div>
  )

  return (
    <div className="card response-viewer">
      <div className="card-header">
        <h2>Propuesta del Curador</h2>
      </div>
      <div className="response-content">
        <pre className="markdown-body">{response}</pre>
      </div>
    </div>
  )
}
