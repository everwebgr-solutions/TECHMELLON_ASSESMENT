import { useState, useEffect } from 'react'
import styles from './PastRuns.module.css'

function cls(v) { return v >= 8 ? 'pass' : v >= 6 ? 'warn' : 'fail' }
function color(v) { return v >= 8 ? 'var(--green)' : v >= 6 ? 'var(--yellow)' : 'var(--red)' }

const CRITERIA = [
  ['understanding',        'Understanding'],
  ['api_correctness',      'API Correctness'],
  ['outcome_confirmation', 'Outcome Confirm.'],
  ['naturalness',          'Naturalness'],
]

export function PastRuns() {
  const [logs, setLogs] = useState([])        // [{filename, meta}]
  const [selected, setSelected] = useState(null)
  const [runData, setRunData] = useState(null)
  const [activeIter, setActiveIter] = useState(null)
  const [diffTab, setDiffTab] = useState('prompt')

  // Load index on mount
  useEffect(() => {
    fetch('/logs')
      .then(r => r.json())
      .then(d => setLogs(d.logs ?? []))
      .catch(() => {})
  }, [])

  function openRun(filename) {
    if (filename === selected) return
    setSelected(filename)
    setRunData(null)
    setActiveIter(null)
    fetch(`/logs/${filename}`)
      .then(r => r.json())
      .then(d => {
        setRunData(d)
        if (d.iterations?.length) setActiveIter(d.iterations[0].iteration)
      })
      .catch(() => {})
  }

  const iteration = runData?.iterations?.find(it => it.iteration === activeIter) ?? null

  return (
    <div className={styles.layout}>
      {/* ── Sidebar ── */}
      <div className={styles.sidebar}>
        <div className={styles.sidebarHeader}>Completed Loops</div>
        <div className={styles.sidebarList}>
          {logs.length === 0
            ? <p className={styles.noData}>No loops completed yet.<br />Run your first loop from the Live View.</p>
            : logs.map((f, idx) => (
                <RunEntry
                  key={f}
                  filename={f}
                  index={logs.length - idx}
                  selected={selected === f}
                  onClick={() => openRun(f)}
                />
              ))
          }
        </div>
      </div>

      {/* ── Detail ── */}
      <div className={styles.detail}>
        {!runData && (
          <div className={styles.detailEmpty}>
            <span className={styles.detailEmptyIcon}>🕐</span>
            Select a loop to view details
          </div>
        )}

        {runData && (
          <>
            {/* Run header */}
            <div className={styles.detailHeader}>
              <div className={styles.detailTitle}>
                Loop — {fmtDate(runData.started_at)}
              </div>
              <div className={styles.detailMeta}>
                {runData.iterations?.length} iteration{runData.iterations?.length !== 1 ? 's' : ''}
                {' · '}
                {runData.termination_reason === 'all_passing' ? 'All criteria passing' : 'Reached max iterations'}
                {runData.performance_summary?.improvement != null && (
                  <span className={styles.improvement}>
                    {' · '}avg {runData.performance_summary.first_iteration_average?.toFixed(1)}
                    {' → '}
                    <span style={{ color: color(runData.performance_summary.final_iteration_average) }}>
                      {runData.performance_summary.final_iteration_average?.toFixed(1)}
                    </span>
                  </span>
                )}
              </div>
            </div>

            {/* Iteration tabs */}
            <div className={styles.iterTabs}>
              {runData.iterations?.map(it => {
                const avg = it.evaluation?.average
                const c   = avg != null ? cls(avg) : null
                return (
                  <button
                    key={it.iteration}
                    className={`${styles.iterTab} ${activeIter === it.iteration ? styles.iterTabActive : ''}`}
                    onClick={() => { setActiveIter(it.iteration); setDiffTab('prompt') }}
                  >
                    Iter {it.iteration}
                    {avg != null && (
                      <span className={`${styles.iterTabScore} ${c ? styles[c] : ''}`}>
                        {avg.toFixed(1)}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* 2-column: conversation | evaluation+changes */}
            {iteration && (
              <div className={styles.iterContent}>
                {/* Left: conversation */}
                <div className={styles.histPanel}>
                  <div className={styles.histPanelLabel}>Conversation</div>
                  {iteration.transcript?.length
                    ? iteration.transcript.map((t, i) => (
                        <div key={i} className={`${styles.message} ${t.role === 'agent' ? styles.agent : styles.user}`}>
                          <div className={styles.role}>{t.role === 'agent' ? 'Sky (Agent)' : 'Customer'}</div>
                          <div className={styles.body}>{t.content}</div>
                        </div>
                      ))
                    : <p className={styles.noData}>No turns recorded.</p>
                  }
                </div>

                {/* Right: scores + tabbed changes */}
                <div className={styles.histPanel}>
                  <div className={styles.histPanelLabel}>Evaluation</div>

                  {iteration.evaluation?.scores && <ScoreBlock ev={iteration.evaluation} iter={activeIter} />}

                  {/* Changes tabs */}
                  <div className={styles.changesTabs}>
                    <button
                      className={`${styles.changesTab} ${diffTab === 'prompt' ? styles.changesTabActive : ''}`}
                      onClick={() => setDiffTab('prompt')}
                    >
                      Prompt Changes
                      <span className={`${styles.count} ${diffTab === 'prompt' ? styles.countActive : ''}`}>
                        {iteration.changes?.prompt_changed ? 1 : 0}
                      </span>
                    </button>
                    <button
                      className={`${styles.changesTab} ${diffTab === 'code' ? styles.changesTabActive : ''}`}
                      onClick={() => setDiffTab('code')}
                    >
                      Code Changes
                      <span className={`${styles.count} ${diffTab === 'code' ? styles.countActive : ''}`}>
                        {iteration.changes?.code_patches?.length ?? 0}
                      </span>
                    </button>
                  </div>

                  {diffTab === 'prompt' && (
                    iteration.changes?.prompt_changed
                      ? <DiffBlock diff={iteration.changes.prompt_diff} />
                      : <p className={styles.noData}>No prompt changes this iteration.</p>
                  )}

                  {diffTab === 'code' && (
                    iteration.changes?.code_patches?.length
                      ? iteration.changes.code_patches.map((p, i) => (
                          <div key={i} className={styles.patchItem}>
                            <div>
                              <span className={styles.patchPath}>{p.file}</span>
                              <span className={styles.patchFn}>::{p.function}</span>
                            </div>
                            <div className={`${styles.patchStatus} ${p.success ? styles.ok : styles.err}`}>
                              {p.success ? '✓' : '✗'} {p.reason}
                            </div>
                            {p.diff
                              ? <DiffBlock diff={p.diff} />
                              : p.success && <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>No source changes recorded.</p>
                            }
                          </div>
                        ))
                      : <p className={styles.noData}>No code patches this iteration.</p>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RunEntry({ filename, index, selected, onClick }) {
  const [meta, setMeta] = useState(null)

  useEffect(() => {
    fetch(`/logs/${filename}`)
      .then(r => r.json())
      .then(d => setMeta(d))
      .catch(() => {})
  }, [filename])

  const ps     = meta?.performance_summary ?? {}
  const reason = meta?.termination_reason
  const date   = fmtDate(meta?.started_at)

  return (
    <div className={`${styles.runEntry} ${selected ? styles.runEntrySelected : ''}`} onClick={onClick}>
      <div className={styles.runEntryTop}>
        <span className={styles.runNum}>Loop #{index}</span>
        <span className={styles.runDate}>{date}</span>
      </div>
      <div className={styles.runMeta}>
        {ps.total_iterations != null && <span>{ps.total_iterations} iteration{ps.total_iterations !== 1 ? 's' : ''}</span>}
        {ps.final_iteration_average != null && (
          <span style={{ color: color(ps.final_iteration_average) }}>avg {ps.final_iteration_average?.toFixed(1)}</span>
        )}
        {reason && (
          <span className={`${styles.reasonBadge} ${reason === 'all_passing' ? styles.allPassing : styles.maxIter}`}>
            {reason === 'all_passing' ? 'All Passing ✓' : 'Max Iterations'}
          </span>
        )}
      </div>
    </div>
  )
}

function ScoreBlock({ ev, iter }) {
  const { scores, average, overall_pass, summary } = ev
  const ac = cls(average)

  return (
    <>
      <div className={styles.evalHeader}>
        <span className={styles.evalIter}>Iteration {iter}</span>
        {average != null && (
          <span className={styles.evalAvg} style={{ color: color(average) }}>
            {average.toFixed(1)}<span className={styles.denom}>/10</span>
          </span>
        )}
        {overall_pass !== undefined && (
          <span className={`${styles.passBadge} ${overall_pass ? styles.pass : styles.fail}`}>
            {overall_pass ? 'PASS' : 'FAIL'}
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
    </>
  )
}

function DiffBlock({ diff }) {
  if (!diff) return null
  return (
    <div className={styles.diffBlock}>
      {diff.split('\n').map((line, i) => {
        let c = ''
        if (line.startsWith('+') && !line.startsWith('+++')) c = styles.add
        else if (line.startsWith('-') && !line.startsWith('---')) c = styles.del
        else if (line.startsWith('@@')) c = styles.hdr
        return <span key={i} className={c}>{line}{'\n'}</span>
      })}
    </div>
  )
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}
