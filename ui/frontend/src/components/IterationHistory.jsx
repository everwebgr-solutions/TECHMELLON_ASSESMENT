import styles from './IterationHistory.module.css'

function cls(v) { return v >= 8 ? 'pass' : v >= 6 ? 'warn' : 'fail' }
function color(v) { return v >= 8 ? 'var(--green)' : v >= 6 ? 'var(--yellow)' : 'var(--red)' }

const SCORE_KEYS = ['understanding', 'api_correctness', 'outcome_confirmation', 'naturalness']

export function IterationHistory({ iterations }) {
  if (iterations.length === 0) {
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>🗂</span>
        No iterations yet.
      </div>
    )
  }

  return (
    <div>
      {[...iterations].reverse().map(it => (
        <div key={it.iteration} className={styles.row}>
          <div className={styles.rowTop}>
            <span className={styles.numBadge}>ITER {it.iteration}</span>
            <span className={styles.scenario}>{it.scenarioId ?? '…'}</span>
            {it.average != null && (
              <span className={styles.avg} style={{ color: color(it.average) }}>
                {it.average.toFixed(1)}
              </span>
            )}
            {it.pass !== null && (
              <span className={`${styles.passBadge} ${it.pass ? styles.pass : styles.fail}`}>
                {it.pass ? 'PASS' : 'FAIL'}
              </span>
            )}
          </div>

          {it.scores
            ? (
              <div className={styles.miniScores}>
                {SCORE_KEYS.map(k => {
                  const v = it.scores[k] ?? 0
                  return (
                    <span key={k} className={`${styles.miniScore} ${styles[cls(v)]}`} title={k}>
                      {v}
                    </span>
                  )
                })}
              </div>
            )
            : <span className={styles.pending}>Evaluating…</span>
          }
        </div>
      ))}
    </div>
  )
}
