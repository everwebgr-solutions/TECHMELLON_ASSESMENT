import styles from './PipelineBar.module.css'

const STEPS = [
  { key: 'initializing', label: 'Setup'        },
  { key: 'simulating',   label: 'Conversation' },
  { key: 'evaluating',   label: 'Evaluation'   },
  { key: 'fixing',       label: 'Changes'      },
]

const ORDER = STEPS.map(s => s.key)

function getStepState(stepKey, activity, allDone) {
  if (allDone) return 'done'
  if (!activity) return 'idle'
  const stepIdx   = ORDER.indexOf(stepKey)
  const activeIdx = ORDER.indexOf(activity)
  if (stepIdx < activeIdx) return 'done'
  if (stepIdx === activeIdx) return 'active'
  return 'idle'
}

export function PipelineBar({ activity, allDone }) {
  return (
    <div className={styles.bar}>
      {STEPS.map((step, i) => {
        const state = getStepState(step.key, activity, allDone)
        return (
          <div key={step.key} className={styles.stepRow}>
            {/* Connector line before step (skip first) */}
            {i > 0 && (
              <div className={`${styles.line} ${state === 'done' || (activity && ORDER.indexOf(activity) >= i) ? styles.lineFilled : ''}`} />
            )}

            <div className={styles.step}>
              <div className={`${styles.circle} ${styles[state]}`}>
                {state === 'active' && <span className={styles.pulse} />}
                {state === 'done'
                  ? <CheckIcon />
                  : <span className={styles.num}>{i + 1}</span>
                }
              </div>
              <span className={`${styles.label} ${state !== 'idle' ? styles.labelActive : ''}`}>
                {step.label}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}
