// Live stage 1: brief, files (with how well each was read), outline, interview. Everything is saved on the server as you go.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ChevronRight, FileText, Globe, ListChecks, Mic, Plus, Send, Sparkles, Trash2, Upload, AlertTriangle, CheckCircle2, SlidersHorizontal } from 'lucide-react';
import { t } from '../i18n.js';
import { api } from './client.js';
import { bytes, errText, nf, NextBar, Spin, Step, useAction, useDebouncedEffect } from './kit.jsx';

const ROLE_LABEL = { source: 'Source', template: 'Template', prior_report: 'Previous report' };

// ------------------------------------------------------------------------------------------ files
function FileInfo({ info }) {
  const [open, setOpen] = useState(false);
  if (!info) return null;
  const st = info.status;
  const pill = st === 'ok' ? ['good', 'Read completely'] : st === 'partial' ? ['warn', 'Read in part'] : st === 'poor' ? ['warn', 'Hardly readable'] : st === 'pending' ? ['info', 'Pages need image analysis'] : null;
  const bits = [info.pages ? t('{n} pages/slides/sheets', { n: info.pages }) : null, info.chars ? t('{n} characters of text', { n: nf(info.chars) }) : null,
    info.vision_pages ? t('{n} pages go to the vision model', { n: info.vision_pages }) : null, info.figures ? t('{n} figures', { n: info.figures }) : null].filter(Boolean);
  const warn = info.warnings || [];
  return (
    <div className="lv-finfo">
      {pill && <span className={`pill ${pill[0]}`}>{t(pill[1])}</span>}
      <span className="muted small">{bits.join(' · ')}</span>
      {warn.length > 0 && <button className="link-btn small" onClick={() => setOpen(!open)}>{t('{n} notes', { n: warn.length })}</button>}
      {open && <ul className="lv-warn">{warn.map((w, i) => <li key={i}>{w}</li>)}</ul>}
    </div>
  );
}

function Files({ rid, files, reload, toast, children }) {
  const [busy, run] = useAction(toast);
  const [over, setOver] = useState(false);
  const inputs = { source: useRef(null), template: useRef(null), prior_report: useRef(null) };
  const upload = (list, role) => run('up', async () => {
    for (const f of [...list]) {
      try { await api.upload(rid, f, role); } catch (e) { toast(`${f.name}: ${errText(e)}`, 'warn'); }
    }
    await reload();
  });
  const del = (f) => run(f.id, async () => { await api.deleteFile(rid, f.id); await reload(); });
  return (
    <div className="lv-files">
      <p className="muted small lv-ftypes">{t('PDF, Word, PowerPoint, Excel, e-mails with attachments, images, scans')}</p>
      <div className={`drop lv-drop${over ? ' over' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files, 'source'); }}>
        <Upload size={22} />
        <strong>{busy === 'up' ? t('Uploading and checking…') : t('Drop files here')}</strong>
        <div className="lv-row center">
          <button className="btn sm" onClick={() => inputs.source.current.click()}>{t('Add sources')}</button>
          <button className="btn sm" onClick={() => inputs.template.current.click()}>{t('Upload template (.pptx)')}</button>
          <button className="btn sm" onClick={() => inputs.prior_report.current.click()}>{t('Add previous report')}</button>
        </div>
        {Object.entries(inputs).map(([role, ref]) => (
          <input key={role} ref={ref} type="file" hidden multiple={role === 'source'} accept={role === 'template' ? '.pptx,.potx' : undefined} onChange={(e) => { upload(e.target.files, role); e.target.value = ''; }} />
        ))}
      </div>
      {files.length > 0 && (
        <ul className="lv-flist">
          {files.map((f) => (
            <li key={f.id}>
              <FileText size={18} />
              <div className="grow"><strong>{f.name}</strong>
                <div className="muted small">{t(ROLE_LABEL[f.role] || f.role)} · {bytes(f.size)}</div>
                <FileInfo info={f.info} /></div>
              <button className="iconbtn" title={t('Remove')} disabled={busy === f.id} onClick={() => del(f)}><Trash2 size={16} /></button>
            </li>
          ))}
        </ul>
      )}
      {children}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ outline
function Outline({ rid, c, reload, toast }) {
  const [secs, setSecs] = useState(null);
  const [notes, setNotes] = useState('');
  const [busy, run] = useAction(toast);
  const dirty = useRef(false);
  useEffect(() => { api.outline(rid).then(setSecs).catch(() => setSecs([])); }, [rid]);
  useDebouncedEffect(() => run('save', async () => { await api.putOutline(rid, secs); dirty.current = false; }), [JSON.stringify(secs)], 900, dirty.current && !!secs);
  const edit = (fn) => { dirty.current = true; setSecs((s) => fn(s.map((x) => ({ ...x })))); };
  const move = (i, d) => edit((s) => { const j = i + d; if (j >= 0 && j < s.length) [s[i], s[j]] = [s[j], s[i]]; return s; });
  const propose = () => run('prop', async () => { const r = await api.proposeOutline(rid); setSecs(r.sections); setNotes(r.notes || ''); await reload(); });
  const list = secs || [];
  const locked = !['SETUP', 'OUTLINE_REVIEW'].includes(c.state);
  return (
    <div className="lv-outline">
      {list.length > 0 && <div className="lv-row end"><button className="btn quiet sm" disabled={!!busy || locked} onClick={propose}>{busy === 'prop' ? <Spin /> : <Sparkles size={15} />} {t('Propose again')}</button></div>}
      {notes && <div className="lv-note"><Sparkles size={16} /><span>{notes}</span></div>}
      {list.length === 0 ? <p className="muted">{t('The template analyst reads your template (or, without one, suggests a structure that fits the topic and the committee).')}</p> : (
        <ol className="lv-outline-list">
          {list.map((s, i) => (
            <li key={s.key} className={s.included ? '' : 'off'}>
              <input type="checkbox" checked={s.included} disabled={locked} onChange={(e) => edit((x) => { x[i].included = e.target.checked; return x; })} aria-label={t('Include')} />
              <div className="grow">
                <input className="lv-in flat" value={s.title} disabled={locked} onChange={(e) => edit((x) => { x[i].title = e.target.value; return x; })} />
                <input className="lv-in flat small muted" value={s.purpose || ''} placeholder={t('Purpose of this section')} disabled={locked} onChange={(e) => edit((x) => { x[i].purpose = e.target.value; return x; })} />
              </div>
              <button className="iconbtn" disabled={locked || i === 0} onClick={() => move(i, -1)} title={t('Move up')}><ArrowUp size={15} /></button>
              <button className="iconbtn" disabled={locked || i === list.length - 1} onClick={() => move(i, 1)} title={t('Move down')}><ArrowDown size={15} /></button>
            </li>
          ))}
        </ol>
      )}
      {!locked && list.length > 0 && <button className="btn quiet sm" onClick={() => edit((x) => [...x, { key: null, title: t('New section'), purpose: '', included: true, suggested_slides: 1 }])}><Plus size={15} /> {t('Add section')}</button>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------ interview
function Interview({ rid, c, toast, hasOutline }) {
  const [data, setData] = useState({ turns: [], statements: [] });
  const [text, setText] = useState('');
  const [busy, run] = useAction(toast);
  const end = useRef(null);
  const load = useCallback(() => api.interview(rid).then(setData).catch(() => {}), [rid]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [data.turns.length]);
  const open = ['OUTLINE_REVIEW', 'COLLECTING'].includes(c.state);
  const send = (done = false) => run('turn', async () => { const v = text; setText(''); await api.turn(rid, v, done); await load(); });
  const speak = useSpeech(lang => setText((x) => `${x} ${lang}`.trim()), toast);
  return (
    <div className="lv-interview">
      {!hasOutline ? <p className="muted">{t('Propose the outline first, then the interviewer can ask about the gaps.')}</p> : (
        <>
          <div className="lv-chat" role="log">
            {data.turns.length === 0 && <p className="muted">{t('No questions yet.')}</p>}
            {data.turns.map((m, i) => <div key={i} className={`lv-msg ${m.role}`}>{m.text}</div>)}
            {busy === 'turn' && <div className="lv-msg agent"><Spin /></div>}
            <div ref={end} />
          </div>
          {open && (
            <div className="lv-compose">
              <textarea className="lv-in" rows={2} value={text} placeholder={data.turns.length ? t('Your answer…') : t('Say or type what you know, or ask for the first question')}
                onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && text.trim()) { e.preventDefault(); send(); } }} />
              <div className="lv-col">
                {speak.supported && <button className={`iconbtn${speak.on ? ' on' : ''}`} title={t('Speak')} onClick={speak.toggle}><Mic size={17} /></button>}
                <button className="btn primary sm" disabled={!!busy} onClick={() => send()}>{data.turns.length || text.trim() ? <Send size={15} /> : <Sparkles size={15} />} {text.trim() ? t('Send') : t('Ask me')}</button>
              </div>
            </div>
          )}
          {open && data.turns.length > 0 && <button className="link-btn small" disabled={!!busy} onClick={() => send(true)}>{t('That is all I know')}</button>}
          {data.statements.length > 0 && (
            <div className="lv-stm"><h3>{t('Captured from your answers')}</h3>
              <ul>{data.statements.map((s) => <li key={s.id}><span className="pill">{s.kind}</span> {s.statement}{s.value != null ? ` (${s.value}${s.unit ? ` ${s.unit}` : ''})` : ''}</li>)}</ul></div>
          )}
        </>
      )}
    </div>
  );
}

/** Speech to text with the browser's own recogniser (Chrome, Edge); nothing is stored by the page. */
function useSpeech(onText, toast) {
  const [on, setOn] = useState(false);
  const rec = useRef(null);
  const Ctor = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  const toggle = () => {
    if (on) { rec.current?.stop(); return; }
    const r = new Ctor();
    r.lang = document.documentElement.lang === 'en' ? 'en-US' : 'de-DE'; r.interimResults = false; r.continuous = true;
    r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i += 1) if (e.results[i].isFinal) onText(e.results[i][0].transcript); };
    r.onerror = (e) => { toast(t('Speech input failed: {e}', { e: e.error }), 'warn'); setOn(false); };
    r.onend = () => setOn(false);
    rec.current = r; r.start(); setOn(true);
  };
  return { supported: !!Ctor, on, toggle };
}

// ------------------------------------------------------------------------------------------ brief form
function Strength({ a }) {
  if (!a) return null;
  const s = a.strength;
  return (
    <div className="lv-strength">
      <div className="lv-score"><b>{s.score}</b><span>%</span></div>
      <div className="grow"><strong>{s.label}</strong><p className="muted small">{s.summary}</p>
        {s.hints?.length > 0 && <ul className="lv-hints">{s.hints.slice(0, 3).map((h, i) => <li key={i}>{h}</li>)}</ul>}</div>
    </div>
  );
}

function StrengthChip({ a }) {
  if (!a) return null;
  const s = a.strength;
  return (
    <details className="lv-chip">
      <summary><span className={`pill ${s.score >= 70 ? 'good' : s.score >= 40 ? 'info' : 'warn'}`}>{t('Brief strength')} {s.score} %</span></summary>
      <div className="lv-chip-pop"><strong>{s.label}</strong><p className="muted small">{s.summary}</p>
        {s.hints?.length > 0 && <ul className="lv-hints">{s.hints.slice(0, 4).map((h, i) => <li key={i}>{h}</li>)}</ul>}</div>
    </details>
  );
}

export default function LiveBrief({ rid, c, reload, lang, st, toast, go }) {
  const [f, setF] = useState(null);
  const [committees, setCommittees] = useState([]);
  const [files, setFiles] = useState([]);
  const [assess, setAssess] = useState(null);
  const [saved, setSaved] = useState(true);
  const [busy, run] = useAction(toast);
  const dirty = useRef(false);
  const [outlineKey, setOutlineKey] = useState(0);
  const [interviewOpen, setInterviewOpen] = useState(false);
  const open = ['SETUP', 'OUTLINE_REVIEW'].includes(c.state);

  useEffect(() => {
    setF({ title: c.title || '', topic: c.topic || '', description: c.description || '', decision_requested: c.decision_requested || '', links: (c.links || []).join('\n'), lang: c.lang || lang, use_web: c.use_web !== false, committee: c.committee || '' });
    api.committees().then(setCommittees).catch(() => {});
    api.files(rid).then(setFiles).catch(() => {});
  }, [rid]); // eslint-disable-line react-hooks/exhaustive-deps
  const loadFiles = useCallback(async () => { setFiles(await api.files(rid)); await reload(); }, [rid, reload]);
  const set = (k) => (e) => { dirty.current = true; setSaved(false); setF((x) => ({ ...x, [k]: e.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e })); };

  useDebouncedEffect(async () => {
    const body = { title: f.title, topic: f.topic, description: f.description, decision_requested: f.decision_requested, lang: f.lang, use_web: f.use_web, links: f.links.split('\n').map((x) => x.trim()).filter(Boolean) };
    const com = committees.find((x) => x.name === f.committee || x.id === f.committee);
    if (com) body.committee_id = com.id;
    try { await api.putCase(rid, body); dirty.current = false; setSaved(true); reload(); } catch (e) { toast(errText(e), 'warn'); }
  }, [JSON.stringify(f)], 900, !!f && dirty.current && open);

  useDebouncedEffect(() => {
    const ctrl = new AbortController();
    api.assess({ lang: f.lang, text: `${f.description}\n${f.decision_requested}`.trim(), overrides: { topic: f.topic || null, committee: f.committee || null }, preset_committee: null,
      files: files.map((x) => ({ name: x.name, kind: x.kind, status: 'ready' })), links: f.links.split('\n').map((x) => x.trim()).filter(Boolean), connectors: {}, answers: {} }, ctrl.signal)
      .then(setAssess).catch(() => {});
    return () => ctrl.abort();
  }, [f?.description, f?.decision_requested, f?.topic, f?.committee, f?.links, files.length, f?.lang], 1200, !!f);

  if (!f) return null;
  const hasOutline = c.state !== 'SETUP';
  const ready = f.topic.trim().length >= 3;
  const body = () => {
    const out = { title: f.title, topic: f.topic, description: f.description, decision_requested: f.decision_requested, lang: f.lang, use_web: f.use_web, links: f.links.split('\n').map((x) => x.trim()).filter(Boolean) };
    const com = committees.find((x) => x.name === f.committee || x.id === f.committee);
    if (com) out.committee_id = com.id;
    return out;
  };
  const propose = () => run('prop', async () => { await api.putCase(rid, body()); dirty.current = false; setSaved(true); await api.proposeOutline(rid); setOutlineKey((k) => k + 1); await reload(); });
  const approve = () => run('approve', async () => { await api.approveOutline(rid); await reload(); go('analysis'); });
  const web = f.use_web && c.web_enabled;
  return (
    <div className="lv-stage narrow">
      <div className="stage-head compact">
        <div><p className="eyebrow">{t('Step 1 · Brief')}</p><h1 className="display md">{t('Tell me what you know')}</h1></div>
        <span className="muted small">{saved ? <><CheckCircle2 size={14} /> {t('Saved')}</> : <><Spin size={13} /> {t('Saving…')}</>}</span>
      </div>
      {!open && <div className="lv-banner info"><ListChecks size={20} /><div><strong>{t('The outline is approved')}</strong><span>{t('The brief is locked while the analysis runs or its results are being reviewed. Start a new version from the report step to change it.')}</span></div></div>}

      <Step n={1} title={t('What is this about?')} hint={t('Write it the way you would explain it to a colleague. The more concrete, the better the analysis.')} done={ready} aside={<StrengthChip a={assess} />}>
        <div className="lv-row">
          <div className="lv-field grow"><label>{t('Topic')}</label><input className="lv-in" value={f.topic} disabled={!open} placeholder={t('What is this report about?')} onChange={set('topic')} /></div>
          <div className="lv-field"><label>{t('Committee')}</label>
            <select className="lv-in" value={committees.find((x) => x.name === f.committee || x.id === f.committee)?.id || ''} disabled={!open} onChange={(e) => { dirty.current = true; setSaved(false); setF((x) => ({ ...x, committee: committees.find((k) => k.id === e.target.value)?.name || '' })); }}>
              <option value="">—</option>{committees.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}</select></div>
        </div>
        <div className="lv-field"><label>{t('What do you know?')}</label>
          <textarea className="lv-in" rows={7} value={f.description} disabled={!open} onChange={set('description')}
            placeholder={t('Background, numbers you already have, options, constraints, who decides, what happened before.')} /></div>
        <div className="lv-field"><label>{t('Decision requested from the committee')}</label>
          <input className="lv-in" value={f.decision_requested} disabled={!open} placeholder={t('e.g. “Approve the award to supplier A”')} onChange={set('decision_requested')} /></div>
        <details className="lv-more">
          <summary><SlidersHorizontal size={14} /> {t('More options')} <span className="muted small">{web ? t('Web research on') : t('Web research off')}</span></summary>
          <div className="lv-more-body">
            <div className="lv-row">
              <div className="lv-field grow"><label>{t('Title')}</label><input className="lv-in" value={f.title} disabled={!open} onChange={set('title')} /></div>
              <div className="lv-field"><label>{t('Language of the report')}</label>
                <select className="lv-in" value={f.lang} disabled={!open} onChange={set('lang')}><option value="de">Deutsch</option><option value="en">English</option></select></div>
            </div>
            <label className={`lv-web${web ? ' on' : ''}${c.web_enabled ? '' : ' off'}`}>
              <input type="checkbox" checked={web} disabled={!open || !c.web_enabled} onChange={set('use_web')} />
              <Globe size={18} />
              <span><strong>{t('Research on the web')} <span className="pill good">{t('recommended')}</span></strong>
                <small>{c.web_enabled ? t('On for every report: the Foundry web search tool looks for market data, benchmarks and news, and every page used is listed as a source. No extra credentials.') : t('Web access is switched off on this server (ALLOW_WEB).')}</small></span>
            </label>
          </div>
        </details>
      </Step>

      <Step n={2} title={t('Add your material')} hint={t('Optional, but this is where the real numbers come from. Each file is read completely; scans and images are read by the vision model.')} done={files.length > 0}>
        <Files rid={rid} files={files} reload={loadFiles} toast={toast}>
          <div className="lv-field"><label>{t('Links')} <span className="muted small">{t('one per line; pages are read and cited')}</span></label>
            <textarea className="lv-in" rows={2} value={f.links} disabled={!open} onChange={set('links')} placeholder="https://…" /></div>
        </Files>
      </Step>

      {hasOutline && (
        <Step n={3} title={t('Outline')} hint={t('Check the structure of the report. Rename, reorder or switch off sections; changes are saved as you type.')} done={c.state !== 'OUTLINE_REVIEW'}>
          <Outline key={outlineKey} rid={rid} c={c} reload={reload} toast={toast} />
        </Step>
      )}

      {hasOutline && (
        <details className="card lv-opt" open={interviewOpen} onToggle={(e) => setInterviewOpen(e.currentTarget.open)}>
          <summary><ChevronRight size={16} className="lv-opt-chev" /> <strong>{t('Add what only you know')}</strong> <span className="muted small">{t('optional · the agent asks, your answers count as your own evidence')}</span></summary>
          <Interview rid={rid} c={c} toast={toast} hasOutline={hasOutline} />
        </details>
      )}

      <NextBar status={!ready ? t('Start with the topic.') : !hasOutline ? t('Next: I draft an outline from your brief and files.') : open ? t('{a} files · the analysis starts when you approve.', { a: files.length }) : t('The outline is approved.')}>
        {!hasOutline && <button className="btn primary lg" disabled={!!busy || !ready} onClick={propose}>{busy === 'prop' ? <Spin /> : <Sparkles size={17} />} {t('Create outline')}</button>}
        {hasOutline && open && <button className="btn primary lg" disabled={!!busy} onClick={approve}>{busy === 'approve' ? <Spin /> : <Sparkles size={17} />} {t('Approve outline and start analysis')}</button>}
        {hasOutline && !open && <button className="btn lg" onClick={() => go('analysis')}>{t('To the analysis')}</button>}
      </NextBar>
    </div>
  );
}
