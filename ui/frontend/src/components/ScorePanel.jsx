import styles from './ScorePanel.module.css'

const CRITERIA = [
  ['understanding',        'Understanding'],
  ['api_correctness',      'API Correctness'],
  ['outcome_confirmation', 'Outcome Confirm.'],
  ['naturalness',          'Naturalness'],
]

function cls(v) { return v >= 8 ? 'pass' : v >= 6 ? 'warn' : 'fail' }
function color(v) { return v >= 8 ? 'var(--green)' : v >= 6 ? 'var(--yellow)' : 'var(--red)' }

export function ScorePanel({ iteration, scores, average, pass, summary, activity }) {
  if (!scores) {
    if (activity === 'evaluating') {
      return (
        <div className={styles.empty}>
          <span className={`${styles.spinner}`} />
          <span className={styles.activityLabel}>Evaluating conversation…</span>
        </div>
      )
    }
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>📊</span>
        No evaluation yet.
      </div>
    )
  }

  const ac = cls(average)

  return (
    <div>
      <div className={styles.evalHeader}>
        <span className={styles.evalIter}>Iteration {iteration}</span>
        {average != null && (
          <span className={styles.evalAvg} style={{ color: color(average) }}>
            {average.toFixed(1)}<span className={styles.denom}>/10</span>
          </span>
        )}
        {pass !== null && (
          <span className={`${styles.passBadge} ${pass ? styles.pass : styles.fail}`}>
            {pass ? 'PASS' : 'FAIL'}
          </span>
        )}
      </div>

      <div className={styles.scoreGrid}>
        {CRITERIA.map(([key, label]) => {
          const v = scores[key] ?? 0
          const c = cls(v)
          return (
            <div key={key} className={styles.scoreCard}>
              <div className={styles.scoreLabel}>{label}</div>
              <div className={styles.scoreValue} style={{ color: color(v) }}>
                {v}<span className={styles.denom}>/10</span>
              </div>
              <div className={styles.barWrap}>
                <div className={`${styles.bar} ${styles[c]}`} style={{ width: `${v * 10}%` }} />
              </div>
            </div>
          )
        })}
      </div>

      {summary && <div className={styles.summary}>{summary}</div>}

      {activity === 'fixing' && (
        <div className={styles.fixingBanner}>
          <span className={styles.spinner} />
          Applying fixes…
        </div>
      )}
    </div>
  )
}
