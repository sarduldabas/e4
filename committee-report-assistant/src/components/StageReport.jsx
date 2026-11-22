import { t, getLang } from '../i18n.js';
import { useEffect, useMemo, useState } from 'react';
import {
  Play, Download, ArrowLeft, ChevronLeft, ChevronRight, Check, AlertTriangle, RefreshCw, Send, Undo2, X, Loader2, FileText, Info,
} from 'lucide-react';
import { SRC, qcText, slideText, slideNotes } from '../data.js';
import { detect, includedSections, reportMeta } from '../workspace.js';
import { ActionBar, Avatar, Modal, SourceIcon, useInterval } from './ui.jsx';
import { Slide, SlideFrame } from './Slide.jsx';

const BUILD_STEPS = ['Mapping 7 sections to the committee template', 'Placing 5 charts and the options table', 'Writing speaker notes', 'Checking every figure against the analysis'];
const shorten = (b) => { const cut = b.search(/[;,(]| – | — /); return cut > 38 ? `${b.slice(0, cut).trim().replace(/[.,;:]$/, '')}.` : b; };

function BuildView({ onBuilt }) {
  const [step, setStep] = useState(0);
  useInterval(() => setStep((s) => s + 1), 700, step <= BUILD_STEPS.length);
  useEffect(() => { if (step > BUILD_STEPS.length) { const tm = setTimeout(onBuilt, 300); return () => clearTimeout(tm); } return undefined; }, [step]); // eslint-disable-line
  return (
    <div className="stage stage-build">
      <header className="stage-head center">
        <p className="eyebrow">{t("Step 3 of 3 · Report")}</p>
        <h1 className="display lg">{t("Composing your")} <em>{t("slides.")}</em></h1>
        <p className="lede">{t("Everything you reviewed goes into the committee template. Each slide stays linked to its analysis section.")}</p>
      </header>
      <div className="build-grid">
        <ol className="run-steps">
          {BUILD_STEPS.map((txt, i) => (
            <li key={txt} className={i < step ? 'done' : i === step ? 'active' : 'todo'}>
              <span className="rs-ico">{i < step ? <Check size={14} strokeWidth={2.6} /> : i === step ? <Loader2 size={14} className="spin" /> : <span className="dot" />}</span>
              <span className="rs-main"><strong>{t(txt)}</strong></span>
            </li>
          ))}
        </ol>
        <div className="skeletons">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="skel" style={{ animationDelay: `${i * 0.12}s` }} />)}</div>
      </div>
    </div>
  );
}

function Present({ slides, ctx, start, onClose }) {
  const [i, setI] = useState(start);
  useEffect(() => {
    const k = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight' || e.key === ' ') setI((x) => Math.min(slides.length - 1, x + 1));
      if (e.key === 'ArrowLeft') setI((x) => Math.max(0, x - 1));
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [slides.length, onClose]);
  return (
    <div className="present" onClick={() => setI((x) => Math.min(slides.length - 1, x + 1))}>
      <button className="iconbtn light" onClick={(e) => { e.stopPropagation(); onClose(); }} aria-label={t("Exit presentation")}><X size={20} /></button>
      <div className="present-slide"><SlideFrame><Slide slide={slides[i]} ctx={{ ...ctx, n: i + 1 }} /></SlideFrame></div>
      <p className="present-hint">{i + 1} / {slides.length} · {t('Arrow keys to move · Esc to close')}</p>
    </div>
  );
}

function ExportModal({ onClose, ws, toast }) {
  const [fmt, setFmt] = useState('pptx');
  const [notes, setNotes] = useState(true);
  const [appendix, setAppendix] = useState(true);
  const [state, setState] = useState('idle');
  const [pct, setPct] = useState(0);
  useInterval(() => setPct((p) => { if (p >= 100) { setState('done'); return 100; } return p + 8; }), 120, state === 'running');
  const name = `Committee_report_FAKOM_2026-12-03_${ws.version}.${fmt}`;
  return (
    <Modal title={t("Export presentation")} onClose={onClose} width={520}
      footer={state === 'done'
        ? <><span className="grow" /><button className="btn primary" onClick={() => { toast(t('Export ready. In the full product the file downloads here.')); onClose(); }}>{t("Done")}</button></>
        : <><span className="grow" /><button className="btn quiet" onClick={onClose}>{t("Cancel")}</button><button className="btn primary" disabled={state === 'running'} onClick={() => { setState('running'); setPct(0); }}>{state === 'running' ? t('Creating file…') : t('Export')}</button></>}>
      {state === 'idle' && (
        <div className="export">
          <div className="seg" role="radiogroup" aria-label={t("Format")}>
            {[['pptx', 'PowerPoint'], ['pdf', 'PDF']].map(([k, l]) => <button key={k} role="radio" aria-checked={fmt === k} className={fmt === k ? 'on' : ''} onClick={() => setFmt(k)}>{l}</button>)}
          </div>
          <label className="check"><input type="checkbox" checked={notes} onChange={(e) => setNotes(e.target.checked)} /> {t("Include speaker notes")}</label>
          <label className="check"><input type="checkbox" checked={appendix} onChange={(e) => setAppendix(e.target.checked)} /> {t("Add source appendix (10 sources)")}</label>
          <p className="muted small">{t('File name: {name}. Version {v} stays editable until you mark it as presented.', { name, v: ws.version })}</p>
        </div>
      )}
      {state !== 'idle' && (
        <div className="export">
          <div className="run-bar"><i style={{ width: `${pct}%` }} /></div>
          <p>{state === 'done' ? <><Check size={16} className="ok" /> {t('{name} is ready.', { name })}</> : t('Placing charts and applying the template…')}</p>
          {state === 'done' && <p className="muted small">{t("Prototype note: file generation runs in the backend (python-pptx or Open XML) in the full product.")}</p>}
        </div>
      )}
    </Modal>
  );
}

export default function StageReport({ ws, setDeck, onBuilt, updateSlides, gotoAnalysis, onBack, toast }) {
  const d = ws.deck;
  const a = ws.analysis;
  const [present, setPresent] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [cmd, setCmd] = useState('');
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);

  const qc = qcText(a.qualCost);
  const det = detect(ws.brief);
  const { committee, dateIso } = reportMeta(ws);
  const slide = d.slides[d.active];
  const ctx = (n) => ({ qc, committee, date: dateIso, n });

  useEffect(() => {
    const k = (e) => {
      const el = e.target;
      if (el.isContentEditable || ['INPUT', 'TEXTAREA'].includes(el.tagName)) return;
      if (e.key === 'ArrowRight') setDeck((x) => ({ ...x, active: Math.min(x.slides.length - 1, x.active + 1) }));
      if (e.key === 'ArrowLeft') setDeck((x) => ({ ...x, active: Math.max(0, x.active - 1) }));
    };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [setDeck]);

  const patchSlide = (id, patch) => setDeck((x) => ({ ...x, slides: x.slides.map((s) => (s.id === id ? { ...s, ...patch } : s)) }));

  const assist = (text) => {
    const cmdText = (text ?? cmd).trim();
    if (!cmdText || busy || !slide) return;
    setCmd(''); setBusy(true);
    const prev = { id: slide.id, bullets: slide.bullets, notes: slide.notes, title: slide.title };
    setTimeout(() => {
      const sq = (s) => slideText(s, slide.qcv);
      if (/short|trim|concise|kürz|kurz|straff/i.test(cmdText)) patchSlide(slide.id, { bullets: slide.bullets.map((b) => shorten(sq(b))) });
      else if (/note|notiz/i.test(cmdText)) patchSlide(slide.id, { notes: t('Talking points: {p}', { p: slide.bullets.map(sq).join(' ') }) });
      else if (/conclusion|title|titel|aussage/i.test(cmdText)) patchSlide(slide.id, { title: sq(slide.title).replace(/[.]$/, '') });
      setLog((l) => [{ text: cmdText, n: d.active + 1, prev, id: Math.random() }, ...l].slice(0, 3));
      setBusy(false);
    }, 1100);
  };
  const undo = (entry) => { patchSlide(entry.prev.id, { bullets: entry.prev.bullets, notes: entry.prev.notes, title: entry.prev.title }); setLog((l) => l.filter((x) => x.id !== entry.id)); };

  const checks = useMemo(() => {
    const secs = includedSections(ws);
    const out = [];
    const usesQc = d.slides.some((s) => ['s1', 's4', 's7'].includes(s.sectionId));
    if (a.qualCost === null && usesQc) out.push({ k: 'warn', t: t('Qualification cost shows a range ({range}) because the conflict is open.', { range: qcText(null) }), act: t('Resolve in Analysis'), go: 's4' });
    else out.push({ k: 'ok', t: t('All figures match the analysis.') });
    const unrev = secs.filter((s) => !a.reviewed[s.id]).length;
    if (unrev) out.push({ k: 'warn', t: t('{a} of {b} sections are not reviewed yet.', { a: unrev, b: secs.length }), act: t('Review'), go: secs.find((s) => !a.reviewed[s.id])?.id });
    else out.push({ k: 'ok', t: t('All sections reviewed.') });
    if (a.gap === null) out.push({ k: 'info', t: t('Capacity beyond 2029 is still an open gap (slide 4).'), act: t('Resolve in Analysis'), go: 's3' });
    const long = d.slides.filter((s) => s.bullets.length > 5 || s.title.length > 140);
    out.push(long.length ? { k: 'warn', t: t('{n} slide(s) exceed template limits.', { n: long.length }) } : { k: 'ok', t: t('Text length within template limits.') });
    out.push({ k: 'ok', t: t('Every content slide links to its sources.') });
    return out;
  }, [ws, d.slides, a, getLang()]); // eslint-disable-line
  const warnCount = checks.filter((c) => c.k === 'warn').length;

  if (d.status === 'building') return <BuildView onBuilt={onBuilt} />;
  if (!slide) return null;

  const stale = d.staleSections.length;
  const staleSlides = d.slides.filter((s) => d.staleSections.includes(s.sectionId));
  const jonasAt = d.slides.findIndex((s) => s.id === 'sl-s4a');

  return (
    <div className="stage stage-report">
      <header className="stage-head compact">
        <div>
          <p className="eyebrow">{t("Step 3 of 3 · Report")}</p>
          <h1 className="display md">{t("Make it yours,")} <em>{t("then present.")}</em></h1>
        </div>
        <div className="expect narrow">
          <div><span className="expect-k">{t("From you")}</span><span>{t("Edit text directly, ask for changes, resolve the checks.")}</span></div>
          <div><span className="expect-k">{t("Then")}</span><span>{t("Export, or present from here.")}</span></div>
        </div>
      </header>

      {stale > 0 && (
        <div className="banner">
          <RefreshCw size={18} />
          <div><strong>{t("The analysis changed after these slides were built")}</strong><span>{t(staleSlides.length === 1 ? '{n} slide affected. Slides you edited by hand elsewhere stay untouched.' : '{n} slides affected. Slides you edited by hand elsewhere stay untouched.', { n: staleSlides.length })}</span></div>
          <button className="btn primary sm" onClick={() => { updateSlides(); toast(t('Slides updated')); }}>{t("Update slides")}</button>
        </div>
      )}

      <div className="rep-grid">
        <aside className="rail" aria-label={t("Slides")}>
          {d.slides.map((s, i) => (
            <button key={s.id} className={`thumb${i === d.active ? ' on' : ''}`} onClick={() => setDeck({ active: i })} aria-label={t('Slide {n}', { n: i + 1 })}>
              <span className="t-n">{i + 1}</span>
              <span className="t-frame"><SlideFrame><Slide slide={s} ctx={ctx(i + 1)} /></SlideFrame></span>
              {i === jonasAt && <span className="t-pres"><Avatar id="jm" size={20} /></span>}
              {d.staleSections.includes(s.sectionId) && <span className="t-stale" title={t("Needs update")} />}
            </button>
          ))}
        </aside>

        <main className="canvas-col">
          <div className="canvas-bar">
            <span className="tpl"><FileText size={14} /> {t(det.template || 'Committee template')}</span>
            <span className="grow" />
            <button className="iconbtn" disabled={d.active === 0} onClick={() => setDeck({ active: d.active - 1 })} aria-label={t("Previous slide")}><ChevronLeft size={18} /></button>
            <span className="small muted">{t('Slide {n} of {total}', { n: d.active + 1, total: d.slides.length })}</span>
            <button className="iconbtn" disabled={d.active === d.slides.length - 1} onClick={() => setDeck({ active: d.active + 1 })} aria-label={t("Next slide")}><ChevronRight size={18} /></button>
          </div>
          <div className="canvas">
            <SlideFrame key={slide.id}>
              <Slide slide={slide} ctx={ctx(d.active + 1)} editable onEdit={(p) => patchSlide(slide.id, p)} />
            </SlideFrame>
          </div>
          <p className="canvas-hint"><Info size={13} /> {t("Click any text on the slide to edit it.")}</p>
          {slide.sources?.length > 0 && (
            <div className="slide-src">
              <span className="muted small">{t("Sources on this slide")}</span>
              {slide.sources.map((n) => <span key={n} className="src-pill" title={t(SRC[n].excerpt)}><SourceIcon kind={SRC[n].kind} size={13} /> {t(SRC[n].name)}</span>)}
            </div>
          )}
        </main>

        <aside className="panel">
          <section className="card pad">
            <h2>{t("Ask for a change")}</h2>
            <form className="chat-in" onSubmit={(e) => { e.preventDefault(); assist(); }}>
              <input value={cmd} onChange={(e) => setCmd(e.target.value)} placeholder={t('Slide {n}: what should change?', { n: d.active + 1 })} aria-label={t("Ask for a change to this slide")} />
              <button className="round solid sm" aria-label={t("Send")} disabled={busy}><Send size={15} /></button>
            </form>
            <div className="chips">{['Shorten the text', 'Add speaker notes', 'Make the title a conclusion'].map((c) => <button key={c} className="opt" onClick={() => assist(t(c))}>{t(c)}</button>)}</div>
            {busy && <p className="working"><Loader2 size={14} className="spin" /> {t('Updating slide {n}…', { n: d.active + 1 })}</p>}
            {log.map((l) => <p key={l.id} className="logline"><Check size={13} className="ok" /> {t('Slide {n}: “{text}”', { n: l.n, text: l.text })} <button className="textlink" onClick={() => undo(l)}><Undo2 size={12} /> {t("Undo")}</button></p>)}
          </section>

          <section className="card pad">
            <div className="card-head"><h2>{t("Checks")}</h2><span className={`pill ${warnCount ? 'warn' : 'good'}`}>{warnCount ? t('{n} to look at', { n: warnCount }) : t('All clear')}</span></div>
            <ul className="checks">
              {checks.map((c, i) => (
                <li key={i} className={c.k}>
                  {c.k === 'ok' ? <Check size={15} /> : <AlertTriangle size={15} />}
                  <span>{c.t}{c.act && <> <button className="textlink" onClick={() => gotoAnalysis(c.go)}>{c.act}</button></>}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="card pad">
            <h2>{t("Speaker notes")} <span className="muted small">· {t('slide {n}', { n: d.active + 1 })}</span></h2>
            <textarea className="notes" value={slideNotes(slide)} onChange={(e) => patchSlide(slide.id, { notes: e.target.value })} placeholder={t("What you want to say on this slide")} aria-label={t("Speaker notes")} rows={4} />
          </section>
        </aside>
      </div>

      <ActionBar>
        <div className="ab-text"><strong>{warnCount ? t(warnCount > 1 ? '{n} checks to look at' : '{n} check to look at', { n: warnCount }) : t('Ready to export')}</strong><span>{t('You can export now and return to change anything. Version {v} stays a draft.', { v: ws.version })}</span></div>
        <button className="btn quiet" onClick={onBack}><ArrowLeft size={16} /> {t("Analysis")}</button>
        <button className="btn" onClick={() => setPresent(true)}><Play size={15} /> {t("Present")}</button>
        <button className="btn primary lg" onClick={() => setExporting(true)}><Download size={17} /> {t("Export")}</button>
      </ActionBar>

      {present && <Present slides={d.slides} ctx={ctx(1)} start={d.active} onClose={() => setPresent(false)} />}
      {exporting && <ExportModal ws={ws} onClose={() => setExporting(false)} toast={toast} />}
    </div>
  );
}
