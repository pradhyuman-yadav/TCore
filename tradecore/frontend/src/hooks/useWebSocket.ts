import { useEffect, useRef } from 'react'
import { useStore } from '../store'

export function useWebSocket(channel: string) {
  const { pushSignal, setWsStatus } = useStore()
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/${channel}`

    function connect() {
      setWsStatus('connecting')
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setWsStatus('open')

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (channel === 'signals') pushSignal(data)
        } catch {}
      }

      ws.onclose = () => {
        setWsStatus('closed')
        setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [channel])
}
