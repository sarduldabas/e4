import { getLang, t } from './i18n.js';
import {
  OUTLINE, SECTIONS, SRC, SAMPLE_FILE_IDS, SAMPLE_TRANSCRIPT, COMMITTEES, CONNECTORS, REPORTS,
  buildSlides, qcText, fmtDate,
} from './data.js';

export const clone = (o) => JSON.parse(JSON.stringify(o));

const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];
const MONTHS_DE = ['januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'dezember'];
const pad = (n) => String(n).padStart(2, '0');
const yearFor = (m) => (m < 10 ? 2027 : 2026); // demo "today" is 22.11.2026
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function parseDate(t) {
  let m = t.match(/\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b/);
  if (m) return `${pad(m[1])}.${pad(m[2])}.${m[3]}`;
  m = t.match(/\b(\d{1,2})\.?\s+(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\b/i);
  if (m) { const mi = MONTHS_DE.indexOf(m[2].toLowerCase()); return `${pad(m[1])}.${pad(mi + 1)}.${yearFor(mi)}`; }
  m = t.match(/\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\b/i);
  if (m) { const mi = MONTHS.indexOf(m[2].toLowerCase()); return `${pad(m[1])}.${pad(mi + 1)}.${yearFor(mi)}`; }
  m = t.match(/\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?\b/i);
  if (m) { const mi = MONTHS.indexOf(m[1].toLowerCase()); return `${pad(m[2])}.${pad(mi + 1)}.${yearFor(mi)}`; }
  return null;
}

function inferTopic(t) {
  const m = t.match(/\bon (?:our |the |my )?([^.,;]{12,90}?)(?:[.,;]|$)/i) || t.match(/\b(?:zu|zur|zum|über)\s+(?:unserer |unserem |der |dem |die |das )?([^.,;]{12,90}?)(?:\s+(?:vorbereiten|besprechen|präsentieren)|[.,;]|$)/i);
  if (m) return cap(m[1].trim());
  const first = t.split(/[.!?]/)[0].trim();
  return first.length >= 12 ? cap(first.slice(0, 80)) : null;
}

/** What the assistant understood from the free text, plus overrides the user typed in. */
export function detect(brief) {
  const txt = brief.text || '';
  const o = brief.overrides || {};
  const preset = COMMITTEES.find((c) => c.id === brief.presetCommittee);
  const byText =
    /fakom/i.test(txt) ? COMMITTEES[0]
      : /technical steering|technische[nr]? lenkungsausschuss/i.test(txt) ? COMMITTEES[1]
        : /investment committee|investitionsausschuss/i.test(txt) ? COMMITTEES[2] : null;
  const known = byText || preset || null;
  const committee = o.committee ?? known?.name ?? null;
  const date = o.date ?? parseDate(txt) ?? (known ? fmtDate(known.date) : null);
  const topic = o.topic ?? inferTopic(txt);
  const audience = o.audience ?? (/senior management|top management|board|geschäftsführung|vorstand|oberes management/i.test(txt) ? 'Senior management' : committee ? t('{committee} members', { committee: t(committee) }) : null);
  const template = o.template ?? known?.template ?? null;
  return { topic, committee, date, audience, template };
}

export function briefStrength(b) {
  const d = detect(b);
  let s = 0;
  if (d.topic) s += 15;
  if (d.committee) s += 10;
  if (d.date) s += 8;
  const words = (b.text || '').trim().split(/\s+/).filter(Boolean).length;
  s += (Math.min(words, 80) / 80) * 17;
  const items = b.files.filter((f) => f.status === 'ready').length + b.links.length;
  s += (Math.min(items, 6) / 6) * 28;
  const conns = Object.values(b.connectors).filter(Boolean).length;
  s += (Math.min(conns, 5) / 5) * 6;
  s += Object.values(b.answers).filter(Boolean).length * 5.33;
  return Math.round(Math.min(100, s));
}

const freshConnectors = () => Object.fromEntries(CONNECTORS.map((c) => [c.id, c.on]));
const fileFromSource = (id) => ({ id: `f${id}`, srcId: id, name: SRC[id].name, kind: SRC[id].kind, detail: SRC[id].detail, status: 'ready' });
export const sampleFiles = () => SAMPLE_FILE_IDS.map(fileFromSource);
export { fileFromSource };

export function baseAnalysis(status) {
  return {
    status, sections: clone(SECTIONS), reviewed: {}, qualCost: null, gap: null, stale: [],
    revising: {}, revisions: {}, edited: {}, comments: {}, chat: [], notify: false,
  };
}

export function blankWorkspace({ committeeId = null, text = '' } = {}) {
  return {
    id: `new-${Date.now()}`, title: 'New committee report', version: 'v1', sample: false,
    brief: {
      text, overrides: {}, presetCommittee: committeeId, files: [], links: [],
      connectors: freshConnectors(), answers: {}, outline: clone(OUTLINE),
    },
    analysis: baseAnalysis('idle'),
    deck: { status: 'idle', slides: [], active: 0, staleSections: [] },
  };
}

export function sampleWorkspace(title) {
  const brief = {
    text: SAMPLE_TRANSCRIPT[getLang()], overrides: {}, presetCommittee: 'fakom', files: sampleFiles(), links: [],
    connectors: freshConnectors(),
    answers: { q1: 'approve', q2: 'yes', q3: 'align' },
    outline: clone(OUTLINE),
  };
  const analysis = baseAnalysis('done');
  analysis.reviewed = { s1: true, s2: true, s6: true };
  analysis.comments = { s4: [{ who: 'jm', text: 'FAKOM asked for a sensitivity analysis in v1. Is it covered now?', when: 'Yesterday, 17:42', resolved: false }] };
  const slides = buildSlides(analysis.sections, { qc: null, title: REPORTS[0].title, committee: 'FAKOM', date: '2026-12-03', version: 'v2' });
  return {
    id: 'r1', title: title || REPORTS[0].title, version: 'v2', sample: true,
    brief, analysis, deck: { status: 'ready', slides, active: 0, staleSections: [] },
  };
}

export const includedSections = (ws) => ws.brief.outline.filter((o) => o.included).map((o) => {
  const s = ws.analysis.sections.find((x) => x.id === o.id);
  return { ...s, title: o.title };
});

export const openItems = (a) => {
  const items = [];
  if (a.qualCost === null) items.push({ id: 'conflict', section: 's4', label: 'Conflict: qualification cost' });
  if (a.gap === null) items.push({ id: 'gap', section: 's3', label: 'Gap: capacity beyond 2029' });
  return items;
};

export const reportMeta = (ws) => {
  const det = detect(ws.brief);
  const c = COMMITTEES.find((x) => x.name === det.committee);
  let dateIso = c?.date || '2026-12-03';
  if (det.date) { const [d, m, y] = det.date.split('.'); if (y) dateIso = `${y}-${m}-${d}`; }
  return { committee: det.committee || 'Committee', dateIso, template: det.template, topic: det.topic || ws.title };
};
