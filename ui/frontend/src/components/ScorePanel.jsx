import { useState } from 'react'
import styles from './ScorePanel.module.css'

const CRITERIA = [
  ['understanding',        'Understanding'],
  ['api_correctness',      'API Correctness'],
  ['outcome_confirmation', 'Outcome Confirm.'],
  ['naturalness',          'Naturalness'],
]

function cls(v) { return v >= 8 ? 'pass' : v >= 6 ? 'warn' : 'fail' }
function color(v) { return v >= 8 ? 'var(--green)' : v >= 6 ? 'var(--yellow)' : 'var(--red)' }

const TYPE_LABELS = { booking: 'Booking', inquiry: 'Inquiry', modification: 'Modification' }
const TYPE_COLORS = { booking: 'var(--accent)', inquiry: 'var(--yellow)', modification: 'var(--green)' }

export function ScorePanel({ iteration, scores, average, pass, summary, toolCalls, conversationType, activity }) {
  const [toolCallsOpen, setToolCallsOpen] = useState(false)
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
            <div
              key={key}
              className={`${styles.scoreCard} ${key === 'api_correctness' && toolCalls?.length ? styles.clickable : ''}`}
              onClick={key === 'api_correctness' && toolCalls?.length ? () => setToolCallsOpen(o => !o) : undefined}
            >
              <div className={styles.scoreLabel}>
                {label}
                {key === 'api_correctness' && toolCalls?.length > 0 && (
                  <span className={styles.toolCallsToggle}>{toolCallsOpen ? '▾' : '▸'} {toolCalls.length} call{toolCalls.length !== 1 ? 's' : ''}</span>
                )}
              </div>
              <div className={styles.scoreValue} style={{ color: color(v) }}>
                {v}<span className={styles.denom}>/10</span>
              </div>
              <div className={styles.barWrap}>
                <div className={`${styles.bar} ${styles[c]}`} style={{ width: `${v * 10}%` }} />
              </div>
              {key === 'api_correctness' && toolCallsOpen && toolCalls?.length > 0 && (
                <div className={styles.toolCallList}>
                  {toolCalls.map((tc, i) => (
                    <div key={i} className={`${styles.toolCallRow} ${tc.error ? styles.tcFail : styles.tcPass}`}>
                      <span className={styles.tcName}>{tc.tool}</span>
                      <span className={styles.tcStatus}>{tc.error ? '✗' : '✓'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {conversationType && (
        <div className={styles.classification}>
          <span className={styles.classLabel}>Classification</span>
          <span
            className={styles.classType}
            style={{ color: TYPE_COLORS[conversationType] ?? 'var(--text2)', borderColor: TYPE_COLORS[conversationType] ?? 'var(--border)' }}
          >
            {TYPE_LABELS[conversationType] ?? conversationType}
          </span>
        </div>
      )}

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
