import { t } from '../i18n.js';
import { Check, ChevronDown, History, Share2, Lock, LayoutGrid } from 'lucide-react';
import { Avatars } from './ui.jsx';
import { briefStrength } from '../workspace.js';
import ModeToggle from '../live/ModeToggle.jsx';

export function Brand({ onClick }) {
  return (
    <button className="brand" onClick={onClick} aria-label={t("Committee Report Assistant home")}>
      <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
      <span className="brand-name">{t("Committee Report Assistant")}</span>
    </button>
  );
}

const STEPS = [
  { n: 1, label: 'Brief', sub: 'Tell me what you know' },
  { n: 2, label: 'Draft', sub: 'Adjust and download' },
];

function caption(n, ws, assessment) {
  if (n === 1) return t('{p}% brief strength', { p: assessment ? assessment.strength.score : briefStrength(ws.brief) });
  const a = ws.analysis;
  if (a.status === 'idle') return t('Not started');
  if (a.status === 'running') return t('Analysing…');
  const d = ws.deck;
  if (d.status === 'idle' || d.status === 'building') return t('Building…');
  return t('{n} slides', { n: d.slides.length });
}

export function LangToggle({ lang, setLang }) {
  return (
    <div className="lang" role="group" aria-label={t('Language')}>
      {[['de', 'Deutsch'], ['en', 'English']].map(([l, name]) => (
        <button key={l} type="button" className={lang === l ? 'on' : ''} aria-pressed={lang === l} title={name} onClick={() => setLang(l)}>{l.toUpperCase()}</button>
      ))}
    </div>
  );
}

export function TopBar({ ws, assessment, stage, canGo, onStage, onHome, onVersions, onShare, lang, setLang, mode, setMode }) {
  return (
    <header className="topbar">
      <div className="topbar-in">
        <div className="tb-left"><Brand onClick={onHome} /></div>

        <nav className="stepper" aria-label={t("Progress")}>
          {STEPS.map((s, i) => {
            const state = stage === s.n ? 'current' : canGo(s.n) && (s.n < stage || (s.n === 2 && ws.analysis.status === 'done') || (s.n === 3 && ws.deck.status === 'ready')) ? 'done' : 'todo';
            return (
              <div key={s.n} className="step-wrap">
                {i > 0 && <span className={`step-line${state !== 'todo' || stage > i ? ' on' : ''}`} />}
                <button className={`step ${state}`} disabled={!canGo(s.n)} onClick={() => onStage(s.n)} aria-current={stage === s.n ? 'step' : undefined}>
                  <span className="step-dot">{state === 'done' ? <Check size={14} strokeWidth={2.4} /> : s.n}</span>
                  <span className="step-text">
                    <span className="step-label">{t(s.label)}</span>
                    <span className="step-cap">{stage === s.n ? t(s.sub) : caption(s.n, ws, assessment)}</span>
                  </span>
                </button>
              </div>
            );
          })}
        </nav>

        <div className="tb-right">
          <ModeToggle mode={mode} setMode={setMode} />
          <LangToggle lang={lang} setLang={setLang} />
          <span className="secure" title={t("Designed to run inside the Volkswagen cloud environment")}><Lock size={13} /> {t("Stays in VW environment")}</span>
          <button className="ghost-pill" onClick={onVersions}><History size={15} /> {ws.version} <span className="muted">{t("· Draft")}</span> <ChevronDown size={14} /></button>
          <Avatars ids={['kw', 'jm', 'ls']} size={28} />
          <button className="btn sm" onClick={onShare}><Share2 size={15} /> {t("Share")}</button>
        </div>
      </div>
    </header>
  );
}

export function HomeBar({ onHome, lang, setLang, mode, setMode }) {
  return (
    <header className="topbar plain">
      <div className="topbar-in">
        <div className="tb-left"><Brand onClick={onHome} /></div>
        <div className="tb-right">
          <ModeToggle mode={mode} setMode={setMode} />
          <LangToggle lang={lang} setLang={setLang} />
          <span className="secure"><Lock size={13} /> {t("Stays in VW environment")}</span>
          <span className="who"><span className="who-name">{t("Katrin Weber")}</span><span className="who-dept">{t("Technical Development")}</span></span>
          <Avatars ids={['kw']} size={32} />
        </div>
      </div>
    </header>
  );
}

export { LayoutGrid };
