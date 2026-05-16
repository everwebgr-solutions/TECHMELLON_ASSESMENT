import { useEffect, useRef } from 'react'
import styles from './ConversationFeed.module.css'

export function ConversationFeed({ turns }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns.length])

  if (turns.length === 0) {
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>💬</span>
        Waiting for loop to start…
      </div>
    )
  }

  return (
    <div className={styles.feed}>
      {turns.map((item, i) => {
        if (item.type === 'divider') {
          return (
            <div key={i} className={styles.divider}>
              <div className={styles.dividerLine} />
              <div className={styles.dividerLabel}>{item.label}</div>
              <div className={styles.dividerLine} />
            </div>
          )
        }
        return (
          <div key={i} className={`${styles.message} ${item.role === 'agent' ? styles.agent : styles.user}`}>
            <div className={styles.role}>{item.role === 'agent' ? 'Sky (Agent)' : 'Customer'}</div>
            <div className={styles.body}>{item.content}</div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
