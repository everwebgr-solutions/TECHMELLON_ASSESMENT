import styles from './Header.module.css'

export function Header({ loopRunning, onStart, onReset }) {
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
