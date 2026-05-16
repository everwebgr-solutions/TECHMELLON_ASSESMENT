import styles from './IterationSidebar.module.css'

function scoreColor(avg) {
  if (avg === undefined || avg === null) return 'var(--muted)'
  if (avg >= 8) return 'var(--green)'
  if (avg >= 5) return 'var(--yellow)'
  return 'var(--red)'
}

export function IterationSidebar({ iterations, activeIteration, maxIterations, onSelect }) {
  return (
    <div className={styles.sidebar}>
      <div className={styles.sidebarHeader}>Iterations</div>
      <div className={styles.list}>
        {iterations.map(it => (
          <button
            key={it.iteration}
            className={`${styles.item} ${activeIteration === it.iteration ? styles.active : ''}`}
            onClick={() => onSelect(it.iteration)}
          >
            <div className={styles.itemTop}>
              <span className={styles.iterNum}>#{it.iteration}</span>
              {it.average !== undefined && (
                <span className={styles.avg} style={{ color: scoreColor(it.average) }}>
                  {it.average.toFixed(1)}
                </span>
              )}
            </div>
            <div className={styles.scenario}>{it.scenarioId ?? '…'}</div>
            <div className={styles.tags}>
              {it.promptChanged && <span className={styles.tag} style={{ color: 'var(--accent)' }}>prompt</span>}
              {it.codePatches > 0 && <span className={styles.tag} style={{ color: 'var(--accent2)' }}>code</span>}
              {it.pass && <span className={styles.tag} style={{ color: 'var(--green)' }}>✓ pass</span>}
            </div>
          </button>
        ))}

        {/* Placeholder slots */}
        {Array.from({ length: Math.max(0, maxIterations - iterations.length) }).map((_, i) => (
          <div key={`placeholder-${i}`} className={styles.placeholder}>
            #{iterations.length + i + 1}
          </div>
        ))}
      </div>
    </div>
  )
}
