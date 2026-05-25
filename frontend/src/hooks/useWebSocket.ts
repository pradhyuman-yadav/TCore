import { useEffect, useRef } from 'react'
import { useStore, PriceTick } from '../store'

export function useWebSocket(channel: string) {
  const { pushSignal, setWsStatus, setLatestTick } = useStore()
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/${channel}`
    let dead = false

    function connect() {
      if (dead) return
      if (channel === 'signals') setWsStatus('connecting')
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (channel === 'signals') setWsStatus('open')
      }

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (channel === 'signals') pushSignal(data)
          if (channel === 'prices' && data.type === 'tick') setLatestTick(data as PriceTick)
        } catch { /* ignore */ }
      }

      ws.onclose = () => {
        if (channel === 'signals') setWsStatus('closed')
        if (!dead) setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => { dead = true; wsRef.current?.close() }
  }, [channel])
}

/** Lightweight hook for price feed — passes ticks directly to a callback (no store re-render). */
export function usePriceFeed(onTick: (tick: PriceTick) => void) {
  const cbRef = useRef(onTick)
  cbRef.current = onTick          // always latest without re-subscribing

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/prices`

    let ws: WebSocket
    let dead = false

    function connect() {
      if (dead) return
      ws = new WebSocket(url)
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'tick') cbRef.current(data as PriceTick)
        } catch { /* ignore */ }
      }
      ws.onclose = () => { if (!dead) setTimeout(connect, 3000) }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => { dead = true; ws?.close() }
  }, [])
}
