import { useCallback, useEffect, useState } from 'react';
import { setLang as applyLang } from './i18n.js';
import { assessBrief, briefPayload } from './api.js';
import { blankWorkspace, sampleWorkspace, detect, includedSections, reportMeta } from './workspace.js';
import { buildSlides, REPORTS, SAMPLE_TRANSCRIPT } from './data.js';
import { TopBar, HomeBar } from './components/TopBar.jsx';
import Home from './components/Home.jsx';
import StageBrief from './components/StageBrief.jsx';
import StageAnalysis from './components/StageAnalysis.jsx';
import StageReport from './components/StageReport.jsx';
import { VersionsDrawer, ShareModal, NotesPanel } from './components/Overlays.jsx';
import { Toasts, useToasts } from './components/ui.jsx';

// What a change in the brief can make outdated in an existing analysis.
const BRIEF_IMPACT = { text: ['s1', 's7'], files: ['s3', 's4'], answers: ['s7'], connectors: ['s3'] };

const merge = (key) => (f) => (w) => ({ ...w, [key]: typeof f === 'function' ? f(w[key]) : { ...w[key], ...f } });

/** Asks the Brief agent (via the backend) to assess the brief. Returns null while offline: the UI then uses its local logic. */
function useBriefAssessment(brief, lang, enabled) {
  const [assessment, setAssessment] = useState(null);
  const payload = enabled && brief ? JSON.stringify(briefPayload(brief, lang)) : null;
  useEffect(() => {
    if (!payload) return undefined;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      assessBrief(JSON.parse(payload), ctrl.signal)
        .then((a) => { if (!ctrl.signal.aborted) setAssessment(a); })
        .catch(() => { if (!ctrl.signal.aborted) setAssessment(null); });
    }, 800); // a model call per keystroke would be wasteful: wait until the user pauses
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [payload]);
  return payload && assessment?.lang === lang ? assessment : null;
}

export default function App() {
  const [view, setView] = useState('home');
  const [ws, setWs] = useState(null);
  const [stage, setStage] = useState(1);
  const [flags, setFlags] = useState({ autoVoice: false, focus: null });
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  // UI language: German by default, switchable via the DE | EN toggle in the top bar.
  const [lang, setLangState] = useState('de');
  const setLang = (l) => {
    setLangState(l);
    // The sample brief is stored text: keep it in the chosen language as long as the user has not edited it.
    setWs((w) => (w && Object.values(SAMPLE_TRANSCRIPT).includes(w.brief.text) ? { ...w, brief: { ...w.brief, text: SAMPLE_TRANSCRIPT[l] } } : w));
  };
  applyLang(lang); // set before children render so every t() call sees the active language
  const [toasts, toast] = useToasts();

  const setBrief = useCallback((f) => setWs(merge('brief')(f)), []);
  const setAnalysis = useCallback((f) => setWs(merge('analysis')(f)), []);
  const setDeck = useCallback((f) => setWs(merge('deck')(f)), []);
  const top = () => window.scrollTo({ top: 0 });

  const briefChanged = useCallback((kind) => {
    setWs((w) => (!w || w.analysis.status !== 'done' || !BRIEF_IMPACT[kind] ? w
      : { ...w, analysis: { ...w.analysis, stale: [...new Set([...w.analysis.stale, ...BRIEF_IMPACT[kind]])] } }));
  }, []);
  const markDeckStale = useCallback((ids) => {
    setWs((w) => (w.deck.status !== 'ready' ? w : { ...w, deck: { ...w.deck, staleSections: [...new Set([...w.deck.staleSections, ...ids])] } }));
  }, []);
  const setIncluded = (id, included) => {
    setBrief((b) => ({ ...b, outline: b.outline.map((o) => (o.id === id ? { ...o, included } : o)) }));
    markDeckStale([id]);
  };

  const canGo = (n) => n === 1 || (n === 2 && ws.analysis.status !== 'idle') || (n === 3 && ws.deck.status !== 'idle');
  const go = (n, focus = null) => { if (!canGo(n)) return; setFlags((f) => ({ ...f, focus })); setStage(n); top(); };

  const startNew = ({ text = '', committeeId = null, autoVoice = false }) => {
    setWs(blankWorkspace({ committeeId, text })); setFlags({ autoVoice, focus: null }); setStage(1); setView('ws'); top();
  };
  const openReport = (r) => {
    setWs(sampleWorkspace(r.title)); setFlags({ autoVoice: false, focus: null }); setStage(r.stage || 2); setView('ws'); top();
  };

  const startAnalysis = () => {
    if (ws.analysis.status === 'idle') setAnalysis({ status: 'running' });
    setStage(2); top();
  };
  const createReport = () => {
    if (ws.deck.status === 'idle') setDeck({ status: 'building' });
    setStage(3); top();
  };

  const slidesCtx = (w) => {
    const m = reportMeta(w);
    return { qc: w.analysis.qualCost, title: m.topic, committee: m.committee, date: m.dateIso, version: w.version };
  };
  const onBuilt = () => setWs((w) => ({ ...w, deck: { status: 'ready', slides: buildSlides(includedSections(w), slidesCtx(w)), active: 0, staleSections: [] } }));
  const updateSlides = () => setWs((w) => {
    const stale = new Set(w.deck.staleSections);
    const byId = Object.fromEntries(w.deck.slides.map((s) => [s.id, s]));
    const fresh = buildSlides(includedSections(w), { ...slidesCtx(w), prev: w.deck.slides });
    const merged = fresh.map((f) => (byId[f.id] && !stale.has(f.sectionId) ? byId[f.id] : f));
    return { ...w, deck: { ...w.deck, slides: merged, staleSections: [], active: Math.min(w.deck.active, merged.length - 1) } };
  });

  useEffect(() => { document.title = 'Committee Report Assistant'; }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const draft = ws && !ws.sample && view === 'home' ? ws : null;
  const assessment = useBriefAssessment(ws?.brief, lang, view === 'ws' && !!ws);

  return (
    <div className="app">
      {view === 'home' ? (
        <>
          <HomeBar onHome={() => setView('home')} lang={lang} setLang={setLang} />
          <Home onNew={startNew} onOpen={openReport} draft={draft} onResume={() => { setView('ws'); top(); }} />
        </>
      ) : (
        <>
          <TopBar ws={ws} assessment={assessment} stage={stage} canGo={canGo} onStage={(n) => go(n)} onHome={() => { setView('home'); top(); }} onVersions={() => setVersionsOpen(true)} onShare={() => setShareOpen(true)} lang={lang} setLang={setLang} />
          <div className="stage-anim" key={`${stage}-${stage === 2 ? ws.analysis.status : stage === 3 ? ws.deck.status : ''}`}>
            {stage === 1 && <StageBrief ws={ws} assessment={assessment} setBrief={setBrief} briefChanged={briefChanged} onStart={startAnalysis} autoVoice={flags.autoVoice} toast={toast} />}
            {stage === 2 && (
              <StageAnalysis ws={ws} setAnalysis={setAnalysis} setIncluded={setIncluded} markDeckStale={markDeckStale}
                onBack={() => go(1)} onNext={createReport} toast={toast} focus={flags.focus} />
            )}
            {stage === 3 && (
              <StageReport ws={ws} setDeck={setDeck} onBuilt={onBuilt} updateSlides={updateSlides}
                gotoAnalysis={(id) => go(2, id)} onBack={() => go(2)} toast={toast} />
            )}
          </div>
          {versionsOpen && <VersionsDrawer ws={ws} onClose={() => setVersionsOpen(false)} toast={toast} />}
          {shareOpen && <ShareModal onClose={() => setShareOpen(false)} toast={toast} />}
        </>
      )}
      <NotesPanel stageKey={view === 'home' ? 'home' : stage} open={notesOpen} setOpen={setNotesOpen} />
      <Toasts items={toasts} />
    </div>
  );
}
