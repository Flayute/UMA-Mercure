import { useState, useEffect, useRef, useCallback } from 'react'

export function usePlayerStatus(sid = 'main') {
  const [status, setStatus] = useState(null)
  const [current, setCurrent] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/status?sid=${encodeURIComponent(sid)}`)

    ws.onopen = () => {
      console.log('WebSocket conectado')
      setConnected(true)
      reconnectAttemptsRef.current = 0
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current)
        reconnectRef.current = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setStatus(data.status)
        setCurrent(data.current)
      } catch (e) {
        console.error('Error parseando WebSocket:', e)
      }
    }

    ws.onclose = () => {
      console.log('WebSocket desconectado, reintentando...')
      setConnected(false)
      // Reconectar con backoff exponencial (máximo 10s)
      const delay = Math.min(1000 * Math.pow(1.5, reconnectAttemptsRef.current), 10000)
      reconnectAttemptsRef.current += 1
      reconnectRef.current = setTimeout(connect, delay)
    }

    ws.onerror = (error) => {
      console.error('Error en WebSocket:', error)
      ws.close()
    }

    wsRef.current = ws
  }, [sid])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
    }
  }, [connect])

  return { status, current, connected }
}
