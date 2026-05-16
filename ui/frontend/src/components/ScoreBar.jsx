import styles from './ScoreBar.module.css'

const CRITERIA = ['understanding', 'api_correctness', 'outcome_confirmation', 'naturalness']
const LABELS = {
  understanding: 'Understanding',
  api_correctness: 'API Correctness',
  outcome_confirmation: 'Outcome Confirm.',
  naturalness: 'Naturalness',
}

function scoreColor(score) {
  if (score >= 8) return 'var(--green)'
  if (score >= 5) return 'var(--yellow)'
  return 'var(--red)'
}

export function ScoreBar({ scores, average, pass, summary }) {
  if (!scores) return null

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.label}>Evaluation Scores</span>
        <span className={styles.avg} style={{ color: scoreColor(average) }}>
          avg {average?.toFixed(1)}
        </span>
        <span className={`${styles.badge} ${pass ? styles.pass : styles.fail}`}>
          {pass ? '✓ PASS' : '✗ FAIL'}
        </span>
      </div>

      <div className={styles.bars}>
        {CRITERIA.map(key => {
          const score = scores[key] ?? 0
          return (
            <div key={key} className={styles.row}>
              <span className={styles.name}>{LABELS[key]}</span>
              <div className={styles.track}>
                <div
                  className={styles.fill}
                  style={{ width: `${score * 10}%`, background: scoreColor(score) }}
                />
              </div>
              <span className={styles.score} style={{ color: scoreColor(score) }}>
                {score}/10
              </span>
            </div>
          )
        })}
      </div>

      {summary && <p className={styles.summary}>{summary}</p>}
    </div>
  )
}
