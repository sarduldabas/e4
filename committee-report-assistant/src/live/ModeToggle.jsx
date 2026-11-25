import { t } from '../i18n.js';

/** Demo | Live. In Demo nothing leaves the browser; in Live the page works with the real backend and agents. */
export default function ModeToggle({ mode, setMode }) {
  return (
    <div className="lang mode" role="group" aria-label={t('Mode')} title={mode === 'live' ? t('Live: real analysis with the backend and the agents') : t('Demo: built-in sample data, nothing is sent')}>
      {[['demo', 'Demo'], ['live', 'Live']].map(([m, name]) => (
        <button key={m} type="button" className={`${mode === m ? 'on' : ''} ${m}`} aria-pressed={mode === m} onClick={() => setMode(m)}>
          {m === 'live' && <i className="live-dot" aria-hidden="true" />}{t(name)}
        </button>
      ))}
    </div>
  );
}
