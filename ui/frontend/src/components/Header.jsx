import styles from './Header.module.css'

export function Header({ loopRunning, onStart, onReset, scenarios, selectedScenario, onScenarioChange }) {
  return (
    <header className={styles.header}>
      <div className={styles.brand}>
        <div className={styles.brandIcon}>✈</div>
        <div>
          <div className={styles.brandTitle}>Sky Airways</div>
          <div className={styles.brandSub}>Refinement Loop Observer</div>
        </div>
      </div>

      <div className={styles.spacer} />

      <StatusBadge running={loopRunning} />

      <select
        className={styles.scenarioSelect}
        value={selectedScenario}
        onChange={e => onScenarioChange(e.target.value)}
        disabled={loopRunning}
      >
        <option value="auto">Auto (round-robin)</option>
        {(scenarios || []).map(s => (
          <option key={s.id} value={s.id}>{s.description}</option>
        ))}
      </select>

      <button
        className={`${styles.btn} ${loopRunning ? styles.btnDisabled : styles.btnPrimary}`}
        onClick={onStart}
        disabled={loopRunning}
      >
        {loopRunning ? '⟳ Running…' : '▶ Start Loop'}
      </button>

      <button className={`${styles.btn} ${styles.btnGhost}`} onClick={onReset}>
        Reset
      </button>
    </header>
  )
}

function StatusBadge({ running }) {
  return (
    <span className={`${styles.badge} ${running ? styles.badgeRunning : styles.badgeIdle}`}>
      <span className={`${styles.dot} ${running ? styles.dotRunning : ''}`} />
      {running ? 'Running' : 'Idle'}
    </span>
  )
}
