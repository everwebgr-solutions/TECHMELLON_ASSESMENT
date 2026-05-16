import { useEffect, useRef, useCallback } from 'react'

/**
 * Connects to the SSE /events endpoint and calls onEvent for each message.
 * The server sends the full history snapshot at the start of every SSE
 * connection, so a page refresh automatically replays prior events.
 * Do NOT also fetch /history — that would deliver every event twice.
 * Reconnects automatically on disconnect.
 */
export function useEventStream(onEvent) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    const es = new EventSource('/events')
    es.onmessage = (e) => {
      try { onEventRef.current(JSON.parse(e.data)) } catch {}
    }
    es.onerror = () => {
      es.close()
      setTimeout(connect, 3000)
    }
    return es
  }, [])

  useEffect(() => {
    const es = connect()
    return () => es.close()
  }, [connect])
}
