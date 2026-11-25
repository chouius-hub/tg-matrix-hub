import { useEffect, useRef, useState } from 'react'
import type { WsEventMessage } from '../types/api'

const MAX_LIVE_EVENTS = 50

/**
 * 订阅后端 /ws/events 实时事件流，断线后自动重连。
 */
export function useWebSocketEvents() {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<WsEventMessage[]>([])
  const [unreadAlerts, setUnreadAlerts] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let active = true
    let retryTimer: number | undefined

    const connect = () => {
      if (!active) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${protocol}//${window.location.host}/ws/events`
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        if (active) setConnected(true)
      }

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as WsEventMessage
          setEvents((prev) => [parsed, ...prev].slice(0, MAX_LIVE_EVENTS))
          if (parsed.type === 'alert' || parsed.type === 'keyword_alert') {
            setUnreadAlerts((n) => n + 1)
          }
        } catch {
          // 忽略非 JSON 消息
        }
      }

      ws.onclose = () => {
        if (!active) return
        setConnected(false)
        retryTimer = window.setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()
    return () => {
      active = false
      if (retryTimer) window.clearTimeout(retryTimer)
      wsRef.current?.close()
    }
  }, [])

  const clearUnreadAlerts = () => setUnreadAlerts(0)

  return { connected, events, unreadAlerts, clearUnreadAlerts }
}

