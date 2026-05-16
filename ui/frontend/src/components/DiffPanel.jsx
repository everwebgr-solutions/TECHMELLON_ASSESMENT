import { useState } from 'react'
import styles from './DiffPanel.module.css'

export function DiffPanel({ diffs, patches, activity }) {
  const [activeTab, setActiveTab] = useState('prompt')

  return (
    <div className={styles.wrap}>
      {/* Tab bar sits in the panel header slot */}
      <div className={styles.tabBar}>
        <TabBtn label="Prompt Changes" count={diffs.length} active={activeTab === 'prompt'} onClick={() => setActiveTab('prompt')} />
        <TabBtn label="Code Changes"   count={patches.length} active={activeTab === 'code'}   onClick={() => setActiveTab('code')} />
      </div>

      <div className={styles.body}>
        {activity === 'fixing' && (
          <div className={styles.fixingBar}>
            <span className={styles.fixingSpinner} />
            Generating and applying fixes…
          </div>
        )}

        {activeTab === 'prompt' && (
          diffs.length === 0
            ? <Empty icon="📝">No prompt changes yet.</Empty>
            : [...diffs].reverse().map((d, i) => (
                <div key={i} className={styles.section}>
                  <div className={styles.sectionHeader}>Iteration {d.iteration}</div>
                  <DiffBlock diff={d.diff} />
                </div>
              ))
        )}

        {activeTab === 'code' && (
          patches.length === 0
            ? <Empty icon="🔧">No code patches yet.</Empty>
            : [...patches].reverse().map((p, i) => (
                <div key={i} className={styles.patchItem}>
                  <div>
                    <span className={styles.patchPath}>{p.file}</span>
                    <span className={styles.patchFn}>::{p.function}</span>
                    <span className={styles.patchIter}>iter {p.iteration}</span>
                  </div>
                  <div className={`${styles.patchStatus} ${p.success ? styles.ok : styles.err}`}>
                    {p.success ? '✓' : '✗'} {p.reason}
                  </div>
                  {p.diff
                    ? <DiffBlock diff={p.diff} />
                    : p.success && <p className={styles.noDiff}>No source changes recorded.</p>
                  }
                </div>
              ))
        )}
      </div>
    </div>
  )
}

function TabBtn({ label, count, active, onClick }) {
  return (
    <button className={`${styles.tab} ${active ? styles.active : ''}`} onClick={onClick}>
      {label}
      <span className={`${styles.count} ${active ? styles.countActive : ''}`}>{count}</span>
    </button>
  )
}

function DiffBlock({ diff }) {
  return (
    <div className={styles.diffBlock}>
      {diff.split('\n').map((line, i) => {
        let cls = ''
        if (line.startsWith('+') && !line.startsWith('+++')) cls = styles.add
        else if (line.startsWith('-') && !line.startsWith('---')) cls = styles.del
        else if (line.startsWith('@@')) cls = styles.hdr
        return <span key={i} className={cls}>{line}{'\n'}</span>
      })}
    </div>
  )
}

function Empty({ icon, children }) {
  return (
    <div className={styles.empty}>
      <span className={styles.emptyIcon}>{icon}</span>
      {children}
    </div>
  )
}
