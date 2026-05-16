import styles from './DiffViewer.module.css'

export function DiffViewer({ diff, patches }) {
  const hasPromptDiff = diff && diff.trim().length > 0
  const hasPatches = patches && patches.length > 0

  if (!hasPromptDiff && !hasPatches) return null

  return (
    <div className={styles.wrap}>
      {hasPromptDiff && (
        <section className={styles.section}>
          <h4 className={styles.title}>Prompt Changes</h4>
          <pre className={styles.diff}>
            {diff.split('\n').map((line, i) => (
              <DiffLine key={i} line={line} />
            ))}
          </pre>
        </section>
      )}

      {hasPatches && patches.map((p, i) => (
        <section key={i} className={styles.section}>
          <h4 className={styles.title}>
            Code Patch — {p.file}::{p.function}
            <span className={`${styles.tag} ${p.success ? styles.tagOk : styles.tagFail}`}>
              {p.success ? 'applied' : 'failed'}
            </span>
          </h4>
          {p.diff && (
            <pre className={styles.diff}>
              {p.diff.split('\n').map((line, j) => (
                <DiffLine key={j} line={line} />
              ))}
            </pre>
          )}
          {p.reason && <p className={styles.reason}>{p.reason}</p>}
        </section>
      ))}
    </div>
  )
}

function DiffLine({ line }) {
  let cls = ''
  if (line.startsWith('+') && !line.startsWith('+++')) cls = 'add'
  else if (line.startsWith('-') && !line.startsWith('---')) cls = 'remove'
  else if (line.startsWith('@@')) cls = 'hunk'

  return <span className={`${styles.line} ${cls ? styles[cls] : ''}`}>{line}{'\n'}</span>
}
