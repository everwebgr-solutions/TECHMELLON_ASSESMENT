import { useState, useCallback, useEffect } from 'react'
import { Header } from './components/Header'
import { ConversationFeed } from './components/ConversationFeed'
import { ScorePanel } from './components/ScorePanel'
import { DiffPanel } from './components/DiffPanel'
import { IterationHistory } from './components/IterationHistory'
import { PastRuns } from './components/PastRuns'
import { PipelineBar } from './components/PipelineBar'
import { useEventStream } from './hooks/useEventStream'
import styles from './App.module.css'

function makeIter(n, scenarioId, scenarioDescription) {
  return { iteration: n, scenarioId, scenarioDescription, turns: [], scores: null, average: null, pass: null, summary: '', toolCalls: [], diffs: [], patches: [] }
}

export default function App() {
  const [tab, setTab] = useState('live')
  const [loopRunning, setLoopRunning] = useState(false)
  const [iterations, setIterations] = useState([])
  const [convItems, setConvItems] = useState([])
  const [currentIteration, setCurrentIteration] = useState(null)
  const [historyCount, setHistoryCount] = useState(0)
  const [activity, setActivity] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const [selectedScenario, setSelectedScenario] = useState('auto')

  useEffect(() => {
    fetch('/scenarios')
      .then(r => r.json())
      .then(d => setScenarios(d.scenarios || []))
      .catch(() => {})
  }, [])

  const handleEvent = useCallback((event) => {
    const { type } = event

    if (type === 'initializing') {
      setLoopRunning(true)
      setActivity('initializing')
    }

    if (type === 'loop_started') {
      setLoopRunning(true)
      setIterations([])
      setConvItems([])
      setCurrentIteration(null)
      // Keep activity at 'initializing' until iteration_started sets it to 'simulating'
    }

    if (type === 'loop_complete') {
      setLoopRunning(false)
      setActivity(null)
      setHistoryCount(c => c + 1)
    }

    if (type === 'iteration_started') {
      const n = event.iteration
      setActivity('simulating')
      setCurrentIteration(n)
      setIterations(prev => {
        if (prev.find(it => it.iteration === n)) return prev
        return [...prev, makeIter(n, event.scenario_id, event.scenario_description)]
      })
      setConvItems(prev => [...prev, {
        type: 'divider',
        label: event.scenario_description ? `Iteration ${n} — ${event.scenario_description}` : `Iteration ${n}`,
      }])
    }

    if (type === 'simulation_complete') {
      setActivity('evaluating')
    }

    if (type === 'conversation_turn') {
      const n = event.iteration
      setIterations(prev => prev.map(it =>
        it.iteration === n
          ? { ...it, turns: [...it.turns, { role: event.role, content: event.content }] }
          : it
      ))
      setConvItems(prev => [...prev, { type: 'message', role: event.role, content: event.content }])
    }

    if (type === 'evaluation_complete') {
      const n = event.iteration
      setActivity('fixing')
      setIterations(prev => prev.map(it =>
        it.iteration === n
          ? { ...it, scores: event.scores, average: event.average, pass: event.overall_pass, summary: event.summary, toolCalls: event.tool_calls || [] }
          : it
      ))
    }

    if (type === 'iteration_complete') {
      setActivity(null)
    }

    if (type === 'prompt_updated') {
      const n = event.iteration
      setIterations(prev => prev.map(it =>
        it.iteration === n
          ? { ...it, diffs: [...it.diffs, { diff: event.diff, iteration: n }] }
          : it
      ))
    }

    if (type === 'code_patched') {
      const n = event.iteration
      setIterations(prev => prev.map(it =>
        it.iteration === n
          ? { ...it, patches: [...it.patches, { file: event.file, function: event.function, success: event.success, reason: event.reason, diff: event.diff, iteration: n, rolledBack: false }] }
          : it
      ))
    }

    if (type === 'rollback') {
      // The rollback fires at iteration N when N's score is worse than N-1.
      // The fixes that were reverted belong to iteration N-1.
      const revertedIter = event.iteration - 1
      setIterations(prev => prev.map(it =>
        it.iteration === revertedIter
          ? {
              ...it,
              patches: it.patches.map(p => ({ ...p, rolledBack: true })),
              diffs:   it.diffs.map(d => ({ ...d, rolledBack: true })),
            }
          : it
      ))
    }
  }, [])

  useEventStream(handleEvent)

  function startLoop() {
    setLoopRunning(true)
    fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_id: selectedScenario === 'auto' ? null : selectedScenario }),
    })
      .then(r => r.json())
      .then(d => { if (d.error) { setLoopRunning(false); alert(d.error) } })
      .catch(e => { setLoopRunning(false); alert(e.message) })
  }

  function resetLoop() {
    fetch('/reset', { method: 'POST' })
      .then(() => {
        setLoopRunning(false)
        setIterations([])
        setConvItems([])
        setCurrentIteration(null)
      })
      .catch(() => {})
  }

  // Collect all diffs and patches across all iterations for the diff panel
  const allDiffs    = iterations.flatMap(it => it.diffs)
  const allPatches  = iterations.flatMap(it => it.patches)
  const currentIter = iterations.find(it => it.iteration === currentIteration) ?? null

  return (
    <div className={styles.app}>
      <Header
        loopRunning={loopRunning}
        onStart={startLoop}
        onReset={resetLoop}
        scenarios={scenarios}
        selectedScenario={selectedScenario}
        onScenarioChange={setSelectedScenario}
      />

      <nav className={styles.tabs}>
        <button className={`${styles.tab} ${tab === 'live' ? styles.tabActive : ''}`} onClick={() => setTab('live')}>
          <LiveIcon /> Live View
        </button>
        <button className={`${styles.tab} ${tab === 'past' ? styles.tabActive : ''}`} onClick={() => setTab('past')}>
          <HistoryIcon /> Past Loops
          <span className={`${styles.tabCount} ${tab === 'past' ? styles.tabCountActive : ''}`}>{historyCount}</span>
        </button>
      </nav>

      {tab === 'live' && (
        <>
          <PipelineBar activity={activity} allDone={!loopRunning && iterations.length > 0 && !!currentIter?.scores} />
          <div className={styles.liveGrid}>
            {/* Top-left: Conversation */}
            <div className={styles.panel}>
              <div className={styles.panelHeader}>💬 Live Conversation</div>
              <div className={styles.panelBody}>
                <ConversationFeed turns={convItems} />
              </div>
            </div>

            {/* Top-right: Evaluation scores */}
            <div className={styles.panel}>
              <div className={styles.panelHeader}>📊 Current Evaluation</div>
              <div className={styles.panelBody}>
                <ScorePanel
                  iteration={currentIteration}
                  scores={currentIter?.scores}
                  average={currentIter?.average}
                  pass={currentIter?.pass}
                  summary={currentIter?.summary}
                  toolCalls={currentIter?.toolCalls}
                  activity={activity}
                />
              </div>
            </div>

            {/* Bottom-left: Diffs — DiffPanel owns its own header (tab bar) */}
            <div className={styles.panel}>
              <DiffPanel diffs={allDiffs} patches={allPatches} activity={activity} />
            </div>

            {/* Bottom-right: Iteration history */}
            <div className={styles.panel}>
              <div className={styles.panelHeader}>🗂 Iteration History</div>
              <div className={styles.panelBody}>
                <IterationHistory iterations={iterations} />
              </div>
            </div>
          </div>
        </>
      )}

      {tab === 'past' && (
        <div className={styles.pastView}>
          <PastRuns />
        </div>
      )}
    </div>
  )
}

function LiveIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
    </svg>
  )
}

function HistoryIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/>
    </svg>
  )
}
