import { t, getLang } from '../i18n.js';
import { useEffect, useState } from 'react';
import {
  Play, Download, ArrowLeft, ChevronLeft, ChevronRight, Check, AlertTriangle, Loader2, FileText, Info, X,
} from 'lucide-react';
import { SRC, qcText, slideText, slideNotes } from '../data.js';
import { detect, openItems, reportMeta } from '../workspace.js';
import { ActionBar, Avatar, Modal, SourceIcon, useInterval } from './ui.jsx';
import { Slide, SlideFrame } from './Slide.jsx';
import AskAI, { useThread } from './AskAI.jsx';

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
          <p className="muted small">{t('File name: {name}. Changes are saved automatically; downloading is recorded.', { name, v: ws.version })}</p>
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

export default function StageReport({ ws, setDeck, setAnalysis, markDeckStale, onBuilt, updateSlides, onBack, toast }) {
  const d = ws.deck;
  const a = ws.analysis;
  const [present, setPresent] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [thread, addMsg, updateMsg] = useThread();
  const [scope, setScope] = useState('slide');

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

  useEffect(() => { if (d.status === 'idle') setDeck({ status: 'building' }); }, [d.status, setDeck]);

  const patchSlide = (id, patch) => setDeck((x) => ({ ...x, slides: x.slides.map((s) => (s.id === id ? { ...s, ...patch } : s)) }));

  const assist = (cmdText) => {
    if (!cmdText || busy || !slide) return;
    setBusy(true);
    const names = { slide: t('This slide'), section: t('This section'), deck: t('Whole deck') };
    const id = addMsg({ text: cmdText, tag: names[scope], pending: true });
    const targets = d.slides.filter((x) => (scope === 'deck' ? true : scope === 'section' ? x.sectionId === slide.sectionId : x.id === slide.id));
    const prev = targets.map((x) => ({ id: x.id, bullets: x.bullets, notes: x.notes, title: x.title }));
    setTimeout(() => {
      const did = new Set();
      targets.forEach((x) => {
        const sq = (q) => slideText(q, x.qcv);
        if (/short|trim|concise|kürz|kurz|straff/i.test(cmdText)) { patchSlide(x.id, { bullets: x.bullets.map((b) => shorten(sq(b))) }); did.add(t('Text shortened')); }
        else if (/note|notiz/i.test(cmdText)) { patchSlide(x.id, { notes: t('Talking points: {p}', { p: x.bullets.map(sq).join(' ') }) }); did.add(t('Speaker notes added')); }
        else if (/conclusion|title|titel|aussage/i.test(cmdText)) { patchSlide(x.id, { title: sq(x.title).replace(/[.]$/, '') }); did.add(t('Title turned into a statement')); }
      });
      if (did.size) {
        const undo = () => { prev.forEach((p) => patchSlide(p.id, { bullets: p.bullets, notes: p.notes, title: p.title })); updateMsg(id, { undo: null, undone: true }); };
        updateMsg(id, { pending: false, reply: t('Done: {what}.', { what: [...did].join(', ') }), undo });
      } else updateMsg(id, { pending: false, tone: 'warn', reply: t('This is a demo: I can shorten the text, add speaker notes or turn titles into statements. The live version understands any request.') });
      setBusy(false);
    }, 1100);
  };
  const decide = (kind, v) => {
    if (kind === 'qc') { setAnalysis((x) => ({ ...x, qualCost: v })); markDeckStale(['s1', 's4', 's7']); if (v) toast(v === 'range' ? t('Both figures will be shown') : t('Using {qc} everywhere, including summary and recommendation', { qc: qcText(v) })); } else { setAnalysis((x) => ({ ...x, gap: v })); markDeckStale(['s3']); }
    updateSlides();
  };

  const items = openItems(a);
  const warnCount = items.length;

  if (d.status === 'building') return <BuildView onBuilt={onBuilt} />;
  if (!slide) return null;

  const jonasAt = d.slides.findIndex((s) => s.id === 'sl-s4a');

  return (
    <div className="stage stage-report">
      <header className="stage-head compact">
        <div>
          <p className="eyebrow">{t("Step 2 · Draft")}</p>
          <h1 className="display md">{t("Your draft is ready.")} <em>{t("Adjust it, then download.")}</em></h1>
        </div>
        <span className="muted small"><Check size={13} /> {t('Saved automatically')}</span>
      </header>

      <div className="rep-grid">
        <aside className="rail" aria-label={t("Slides")}>
          {d.slides.map((s, i) => (
            <button key={s.id} className={`thumb${i === d.active ? ' on' : ''}`} onClick={() => setDeck({ active: i })} aria-label={t('Slide {n}', { n: i + 1 })}>
              <span className="t-n">{i + 1}</span>
              <span className="t-frame"><SlideFrame><Slide slide={s} ctx={ctx(i + 1)} /></SlideFrame></span>
              {i === jonasAt && <span className="t-pres"><Avatar id="jm" size={20} /></span>}
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
          <AskAI
            scopes={[{ key: 'slide', label: t('This slide') }, { key: 'section', label: t('This section') }, { key: 'deck', label: t('Whole deck') }]}
            scope={scope} onScope={setScope}
            target={scope === 'slide' ? t('Slide {n}', { n: d.active + 1 }) : scope === 'section' ? t('The section of slide {n}', { n: d.active + 1 }) : t('All {n} slides', { n: d.slides.length })}
            thread={thread} busy={busy} toast={toast} onSend={assist}
            placeholder={scope === 'slide' ? t('e.g. “Make the three figures easier to compare and cut the second bullet”') : scope === 'section' ? t('e.g. “Go into more detail on the risks and name the cost per option”') : t('e.g. “Shorter overall, for senior management, with more focus on the decision”')}
          />

          <section className="card pad">
            <div className="card-head"><h2>{t("Needs your attention")}</h2><span className={`pill ${warnCount ? 'warn' : 'good'}`}>{warnCount ? t('{n} to look at', { n: warnCount }) : t('All clear')}</span></div>
            {items.length === 0 && <p className="muted small">{t('Every statement on the slides is backed by a source. You can download the draft any time.')}</p>}
            {items.map((it) => (
              <div key={it.id} className="attn-item">
                <p><AlertTriangle size={14} /> {it.id === 'conflict' ? t('Two sources give different qualification costs. Which should the slides use?') : t('Capacity beyond 2029 is not covered by the sources.')}</p>
                <div className="chips">
                  {it.id === 'conflict' ? <>
                    <button className="opt" onClick={() => decide('qc', '14.2')}>{qcText('14.2')}</button>
                    <button className="opt" onClick={() => decide('qc', '15.1')}>{qcText('15.1')}</button>
                    <button className="opt" onClick={() => decide('qc', 'range')}>{t('Show range')}</button>
                  </> : <>
                    <button className="opt" onClick={() => decide('gap', 'requested')}>{t('Ask Procurement')}</button>
                    <button className="opt" onClick={() => decide('gap', 'assumption')}>{t('Treat as assumption')}</button>
                    <button className="opt" onClick={() => decide('gap', 'open')}>{t('Leave open')}</button>
                  </>}
                </div>
              </div>
            ))}
          </section>

          <section className="card pad">
            <h2>{t("Speaker notes")} <span className="muted small">· {t('slide {n}', { n: d.active + 1 })}</span></h2>
            <textarea className="notes" value={slideNotes(slide)} onChange={(e) => patchSlide(slide.id, { notes: e.target.value })} placeholder={t("What you want to say on this slide")} aria-label={t("Speaker notes")} rows={4} />
          </section>
        </aside>
      </div>

      <ActionBar>
        <div className="ab-text"><strong>{warnCount ? t(warnCount > 1 ? '{n} points need attention' : '{n} point needs attention', { n: warnCount }) : t('Ready to download')}</strong><span>{t('Nothing here stops you from downloading the draft.')}</span></div>
        <button className="btn quiet" onClick={onBack}><ArrowLeft size={16} /> {t("Brief")}</button>
        <button className="btn" onClick={() => setPresent(true)}><Play size={15} /> {t("Present")}</button>
        <button className="btn primary lg" onClick={() => setExporting(true)}><Download size={17} /> {t("Download PowerPoint")}</button>
      </ActionBar>

      {present && <Present slides={d.slides} ctx={ctx(1)} start={d.active} onClose={() => setPresent(false)} />}
      {exporting && <ExportModal ws={ws} onClose={() => setExporting(false)} toast={toast} />}
    </div>
  );
}
