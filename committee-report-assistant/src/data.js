// ---------------------------------------------------------------------------
// Demo data. Everything here is mock content for the front-end prototype.
// Replace with API responses from the COE4 backend / Foundry agents later.
// ---------------------------------------------------------------------------

import { t, getLang } from './i18n.js';

const UTC = (iso) => { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d); };
export const TODAY_ISO = '2026-11-22';
export const daysUntil = (iso) => Math.round((UTC(iso) - UTC(TODAY_ISO)) / 864e5);
export const fmtDate = (iso) => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };

export const USER = { name: 'Katrin Weber', first: 'Katrin', initials: 'KW', dept: 'Technical Development' };

export const PEOPLE = [
  { id: 'kw', name: 'Katrin Weber', initials: 'KW', color: 'var(--avatar-1)', role: 'Owner', note: 'You' },
  { id: 'jm', name: 'Jonas Meier', initials: 'JM', color: 'var(--avatar-2)', role: 'Editor', note: 'Viewing slide 5' },
  { id: 'ls', name: 'Lena Schulz', initials: 'LS', color: 'var(--avatar-3)', role: 'Reviewer', note: 'Last seen yesterday' },
];

export const COMMITTEES = [
  { id: 'fakom', name: 'FAKOM', date: '2026-12-03', template: 'FAKOM standard template · 12 slides', hasReport: true },
  { id: 'tsc', name: 'Technical Steering Committee', date: '2026-12-17', template: 'Committee standard template · 10 slides', hasReport: false },
  { id: 'ic', name: 'Investment Committee', date: '2027-01-14', template: 'Investment template · 14 slides', hasReport: false },
];

export const REPORTS = [
  { id: 'r1', title: 'Dual-sourcing strategy for high-voltage battery cells', committee: 'FAKOM', date: '2026-12-03', version: 'v2', status: 'Draft', stage: 2, edited: 'Today, 23:41', people: ['kw', 'jm', 'ls'] },
  { id: 'r2', title: 'Module supply: volume split and review gate', committee: 'FAKOM', date: '2025-06-18', version: 'v1', status: 'Decided', stage: 3, edited: '18.06.2025', people: ['kw', 'ls'] },
  { id: 'r3', title: 'Charging partner shortlist', committee: 'Technical Steering Committee', date: '2026-10-08', version: 'v3', status: 'Presented', stage: 3, edited: '09.10.2026', people: ['kw', 'jm'] },
];

// ----------------------------- Sources -------------------------------------
export const SOURCES = [
  { id: 1, kind: 'pptx', name: 'Supplier_A_Offer_v3.pptx', origin: 'Uploaded', loc: 'Slide 7 and 11', detail: '18 slides · 4 charts · 2 tables', excerpt: 'Weighted average cell price 2027–2032: EUR 69.0 per kWh at 32 GWh annual call-off. Price steps reviewed yearly against the public index.' },
  { id: 2, kind: 'pdf', name: 'Supplier_B_Proposal.pdf', origin: 'Uploaded', loc: 'Page 9 and 12', detail: '24 pages · 3 charts', excerpt: 'Offer for a 40% volume share, average EUR 70.5 per kWh over 2027–2032. Capacity at the standard plant: 6 GWh (2027), 12 GWh (2028), 18 GWh (2029). A regional plant is offered at EUR 74.25 per kWh.' },
  { id: 3, kind: 'xlsx', name: 'Cost_model_Q3.xlsx', origin: 'Uploaded', loc: 'Sheets Options, Volumes, Exposure', detail: '6 sheets · price curves', excerpt: 'Annual volume 32 GWh (about 400,000 vehicles at 80 kWh). Premium option 2 vs option 1: EUR 0.6 per kWh. Qualification budget (sheet Options): EUR 15.1M. Contribution margin per vehicle: EUR 4,500.' },
  { id: 4, kind: 'mail', name: 'RE: Cell qualification timeline', origin: 'Uploaded', loc: 'Message from J. Meier, 14.10.2026', detail: 'Email thread · 7 messages', excerpt: 'Qualification effort for the second source is EUR 14.2M including sample cells and test capacity. First volume about 14 months after contract award.' },
  { id: 5, kind: 'chat', name: 'Teams export: Sourcing sync', origin: 'Uploaded', loc: 'Messages of 29.10. and 03.11.', detail: 'Chat export · 212 messages', excerpt: 'Supply interruption scenario agreed with Production: six weeks without cells stops roughly 7,700 vehicles per week.' },
  { id: 6, kind: 'pptx', name: 'FAKOM_Report_2025-Q2.pptx', origin: 'Uploaded', loc: 'Slides 4 and 9', detail: 'Previous FAKOM report · used as precedent', excerpt: 'Decision FAKOM 18.06.2025: dual sourcing for modules, 60/40 volume split, review gate after 12 months of dual supply.' },
  { id: 7, kind: 'confluence', name: 'Battery Platform: Sourcing Strategy', origin: 'Confluence', loc: 'Section 2, Current situation', detail: 'Internal page', excerpt: 'All high-voltage cells for the platform are currently sourced from Supplier A. Supply contract runs until 2032.' },
  { id: 8, kind: 'jira', name: 'BAT-2231 Cell qualification status', origin: 'Jira', loc: 'Description and comments', detail: 'Internal ticket', excerpt: 'Qualification plan: samples Q2 2027, validation Q3 and Q4 2027, release January 2028, first volume March 2028.' },
  { id: 9, kind: 'wiki', name: 'Cell supplier guidelines', origin: 'Wiki', loc: 'Chapter 4', detail: 'Internal page', excerpt: 'Strategic components require at least two qualified sources before start of production.' },
  { id: 10, kind: 'web', name: 'Cell price outlook 2026–2030', origin: 'Public web', loc: 'Summary table', detail: 'Industry price outlook', excerpt: 'Average cell prices are expected to fall by about 2% per year through 2030. Regional production may qualify for local-content incentives; details are still pending.' },
];
export const SRC = Object.fromEntries(SOURCES.map((s) => [s.id, s]));
export const SAMPLE_FILE_IDS = [1, 2, 3, 4, 5, 6];
export const CONNECTORS = [
  { id: 'confluence', label: 'Confluence', hint: 'Sourcing strategy page', on: true },
  { id: 'jira', label: 'Jira', hint: 'BAT-2231', on: true },
  { id: 'wiki', label: 'Wiki', hint: 'Supplier guidelines', on: true },
  { id: 'web', label: 'Public web', hint: 'Price outlooks', on: true },
  { id: 'outlook', label: 'Outlook', hint: 'Mails with J. Meier', on: false },
  { id: 'sharepoint', label: 'SharePoint', hint: 'Team folder', on: false },
  { id: 'teams', label: 'Teams', hint: 'Sourcing sync chat', on: false },
];

// ------------------------------- Brief -------------------------------------
export const SAMPLE_TRANSCRIPT = {
  en:
    'I need to prepare the FAKOM report for 3 December on our dual-sourcing strategy for high-voltage battery cells. ' +
    'Today everything comes from Supplier A, and the guideline wants two qualified sources before start of production. ' +
    'I am comparing a single source, a 60/40 split with Supplier B, and a version with a regional plant for Supplier B. ' +
    'I think the 60/40 split is the right one, but the committee will want to see cost, risk and timeline. ' +
    'Last time they asked for a sensitivity analysis, so please include that.',
  de:
    'Ich muss den FAKOM-Bericht für den 3. Dezember zu unserer Dual-Sourcing-Strategie für Hochvolt-Batteriezellen vorbereiten. ' +
    'Heute kommt alles von Lieferant A, und die Richtlinie verlangt vor Produktionsstart zwei qualifizierte Quellen. ' +
    'Ich vergleiche eine Einzelquelle, eine 60/40-Aufteilung mit Lieferant B und eine Variante mit einem regionalen Werk für Lieferant B. ' +
    'Ich halte die 60/40-Aufteilung für richtig, aber das Gremium wird Kosten, Risiko und Zeitplan sehen wollen. ' +
    'Beim letzten Mal wurde eine Sensitivitätsanalyse gefordert, bitte nehmen Sie diese auf.',
};

export const OUTLINE = [
  { id: 's1', title: 'Management summary', included: true },
  { id: 's2', title: 'Background and scope', included: true },
  { id: 's3', title: 'Supplier landscape', included: true },
  { id: 's4', title: 'Options and cost', included: true },
  { id: 's5', title: 'Risks and mitigations', included: true },
  { id: 's6', title: 'Timeline and milestones', included: true },
  { id: 's7', title: 'Recommendation and next steps', included: true },
];

// Offline fallback for the Brief agent's questions (the agent service returns the same shape). Answers are stored as option ids.
export const BRIEF_QUESTIONS = [
  { id: 'q1', text: 'What do you need from the committee?', options: [{ id: 'approve', label: 'Approve an option' }, { id: 'info', label: 'For information' }, { id: 'budget', label: 'Release budget' }, { id: 'postpone', label: 'Postpone' }] },
  { id: 'q2', text: 'Do you already favour an option?', options: [{ id: 'yes', label: 'Yes, dual source 60/40' }, { id: 'compare', label: 'Not yet, compare first' }] },
  { id: 'q3', text: 'Should this stay consistent with an earlier decision?', textWithPrecedent: 'I found last year’s FAKOM report. Should this stay consistent with its decisions?', options: [{ id: 'align', label: 'Yes, align with it' }, { id: 'fresh', label: 'No, start fresh' }] },
];

// ------------------------------- Analysis ----------------------------------
// Text tokens: {n} = citation to source n, %QC% = qualification cost (changes when the conflict is resolved).
export const qcText = (qualCost) => {
  const de = getLang() === 'de';
  if (qualCost === '14.2') return de ? '14,2 Mio. €' : '€14.2M';
  if (qualCost === '15.1') return de ? '15,1 Mio. €' : '€15.1M';
  return de ? '14,2–15,1 Mio. €' : '€14.2–15.1M';
};

/** Renders stored slide/section text for display: translate, fill the qualification-cost token, drop citation markers. */
export const slideText = (raw, qcv) => t(raw).replace(/%QC%/g, qcText(qcv)).replace(/\{\d+\}/g, '').trim();
export const slideNotes = (s) => (s.notes != null ? s.notes : t('Key message: {m}', { m: slideText(s.title, s.qcv) }));

export const OPTIONS = [
  { id: 1, name: 'Single source', sub: 'Supplier A only', cost: 69.0, premium: null, qual: '–', first: 'In production', risk: 4.1 },
  { id: 2, name: 'Dual source 60/40', sub: 'A 60% · B 40%', cost: 69.6, premium: 0.6, qual: '%QC%', first: 'Mar 2028', risk: 2.3, recommended: true },
  { id: 3, name: 'Dual source, EU plant', sub: 'A 60% · B 40% from EU plant', cost: 71.1, premium: 2.1, qual: '€18.5M', first: 'Nov 2028', risk: 1.8 },
];

export const PRICE_SERIES = {
  years: [2027, 2028, 2029, 2030, 2031, 2032],
  a: [71.5, 70.3, 69.4, 68.5, 67.7, 66.6],
  b: [73.0, 71.8, 70.8, 69.9, 69.1, 68.4],
  market: [74.5, 72.4, 70.5, 69.0, 67.8, 66.8],
};
export const CAPACITY = [
  { year: 2027, gwh: 6 }, { year: 2028, gwh: 12 }, { year: 2029, gwh: 18 }, { year: 2030, gwh: null }, { year: 2031, gwh: null },
];
export const RISKS = [
  { id: 'R1', name: 'Supplier B misses qualification', l: 2, i: 3, mitigation: 'Gate reviews after each sample batch; contract extension option with Supplier A as fallback.' },
  { id: 'R2', name: 'Premium rises with volume', l: 1, i: 2, mitigation: 'Price steps tied to the public index; review in the 12-month gate.' },
  { id: 'R3', name: 'Capacity at B short of 40% after 2029', l: 2, i: 2, mitigation: 'Request written capacity commitment before contract award.' },
  { id: 'R4', name: 'Quality diverges between suppliers', l: 2, i: 3, mitigation: 'Common cell specification, shared incoming inspection plan.' },
  { id: 'R5', name: 'Supply interruption during ramp-up', l: 1, i: 3, mitigation: 'Safety stock of four weeks until release in January 2028.' },
];
export const MILESTONES = [
  { id: 'm1', label: 'FAKOM decision', type: 'ms', at: 2, text: '03.12.2026' },
  { id: 'm2', label: 'Contract award', type: 'ms', at: 3, text: 'Jan 2027' },
  { id: 'b1', label: 'Sample qualification', type: 'bar', from: 6, to: 15, text: 'Q2–Q4 2027' },
  { id: 'm3', label: 'Release', type: 'ms', at: 15, text: 'Jan 2028' },
  { id: 'm4', label: 'First volume from B', type: 'ms', at: 17, text: 'Mar 2028' },
  { id: 'b2', label: 'Dual-supply period', type: 'bar', from: 17, to: 29, text: '12 months' },
  { id: 'm5', label: 'Review gate', type: 'ms', at: 29, text: 'Mar 2029' },
];

export const SECTIONS = [
  {
    id: 's1', confidence: 'high', sources: [3, 5, 7, 9],
    headline: 'Approve dual sourcing with Supplier B: a premium of €0.6 per kWh removes our single point of failure.',
    bullets: [
      'Today 100% of high-voltage cells come from Supplier A, and the supplier guideline requires two qualified sources before start of production.{7}{9}',
      'The recommended option 2 (60/40 split) costs €0.6 per kWh more than single sourcing, about €19M per year at 32 GWh.{1}{2}{3}',
      'A six-week supply interruption would stop roughly 46,000 vehicles, about ten times the annual premium.{3}{5}',
      'One-time qualification effort is %QC%; first volume from Supplier B follows in March 2028.{3}{4}{8}',
    ],
    decision: 'Decision requested: approve option 2 and release the qualification budget of %QC%.',
  },
  {
    id: 's2', confidence: 'high', sources: [6, 7, 9],
    headline: 'The platform’s cell supply rests on one supplier, which the supplier guideline no longer allows for strategic components.',
    bullets: [
      'Supplier A delivers all cells for the platform today, under a contract that runs until 2032.{7}',
      'Chapter 4 of the supplier guidelines requires at least two qualified sources for strategic components.{9}',
      'FAKOM approved a 60/40 volume split with a 12-month review gate for module supply on 18.06.2025; this proposal follows that precedent.{6}',
      'Scope: high-voltage cells for 2027–2032. Modules and packs are out of scope.{7}',
    ],
  },
  {
    id: 's3', confidence: 'medium', sources: [1, 2, 3, 10],
    headline: 'Supplier B’s offer sits 2–3% above Supplier A and tracks the market; capacity beyond 2029 is not yet confirmed.',
    bullets: [
      'Supplier B offers €70.5 per kWh on average for 2027–2032, 2–3% above Supplier A at €69.0 per kWh.{1}{2}{3}',
      'The public price outlook expects cell prices to fall by about 2% per year, so both offers move with the market.{10}',
      'Stated capacity at Supplier B grows from 6 GWh in 2027 to 18 GWh in 2029, enough for a 40% share of 12.8 GWh. Nothing is stated beyond 2029.{2}',
    ],
    visuals: ['capacity'],
  },
  {
    id: 's4', confidence: 'medium', sources: [1, 2, 3, 4],
    headline: 'Option 2 delivers about 80% of the risk reduction of option 3 at under 30% of its cost premium.',
    bullets: [
      'Option 2 lowers the supply risk score from 4.1 to 2.3; option 3 reaches 1.8 but adds €2.1 per kWh instead of €0.6.{2}{3}',
      'Sensitivity: each 10 points of volume moved to Supplier B add about €0.15 per kWh. A 50/50 split costs €0.75 per kWh more, a 70/30 split €0.45.{3}',
      'Option 3 qualifies later (November 2028) and needs €18.5M one-time effort; the local-content benefit is not yet confirmed.{2}{10}',
    ],
    visuals: ['table', 'cost', 'price'],
  },
  {
    id: 's5', confidence: 'medium', sources: [3, 4, 8],
    headline: 'Two of five risks rate high; both are covered by a fallback to Supplier A volume.',
    bullets: [
      'Qualification failure and quality divergence are the high risks; a contract extension with Supplier A keeps supply secure in both cases.{4}{8}',
      'Safety stock of four weeks covers the period until release in January 2028.{8}',
    ],
    visuals: ['risk'],
  },
  {
    id: 's6', confidence: 'high', sources: [4, 8],
    headline: 'First volume from Supplier B arrives in March 2028, 14 months after contract award in January 2027.',
    bullets: [
      'Qualification is the critical path, with sample gates in Q2, Q3 and Q4 2027.{8}',
      'Release is planned for January 2028; the 12-month review gate follows in March 2029.{6}{8}',
    ],
    visuals: ['timeline'],
  },
  {
    id: 's7', confidence: 'high', sources: [3, 6, 8],
    headline: 'Approve option 2 and review the volume split after 12 months of dual supply.',
    bullets: [
      'FAKOM approval on 03.12.2026, contract award to Supplier B in January 2027.{8}',
      'Release the qualification budget of %QC% for sample cells and test capacity.{3}{4}',
      'Review gate in March 2029: confirm or change the 60/40 split based on quality, price and capacity.{6}',
    ],
  },
];

export const COMMITTEE_QA = [
  { q: 'Is the premium justified by the expected loss?', a: 'At a one-in-ten-years chance of a six-week outage, the expected loss is about €21M per year, close to the €19M premium. The case rests on guideline compliance and exposure size, not on expected value alone. Say so openly.', cites: [3, 5, 9] },
  { q: 'How does this compare to the module decision of June 2025?', a: 'Same structure: 60/40 split and a 12-month review gate. The difference is that cells carry about ten times the volume exposure of modules.', cites: [6] },
  { q: 'When can we change the volume split?', a: 'At the review gate in March 2029, after twelve months of dual supply. Earlier changes need a new FAKOM decision.', cites: [6, 8] },
  { q: 'What happens if Supplier B misses qualification?', a: 'Supplier A volume continues under a contract extension, and four weeks of safety stock cover the gap. Option 2 then reverts to single sourcing without penalty.', cites: [4, 8] },
];

export const CHAT_SUGGESTIONS = ['Why is option 3 more expensive?', 'What changed since v1?', 'Challenge the recommendation'];
export function replyTo(msg) {
  const m = msg.toLowerCase();
  if (m.includes('option 3') || m.includes('option 3') || m.includes('expensive') || m.includes('eu plant') || m.includes('teuer') || m.includes('werk')) return { text: 'Option 3 buys cells for Supplier B’s 40% share from a regional plant at €74.25 per kWh instead of €70.5 per kWh at the standard plant. That lifts the blended cost to €71.1 per kWh.', cites: [2, 3] };
  if (m.includes('v1') || m.includes('change') || m.includes('änder') || m.includes('geändert')) return { text: 'v2 adds the TCO sensitivity, Supplier B capacity data to 2029 and a review gate for the volume split. These are the three points FAKOM raised on 05.11.2026.', cites: [6] };
  if (m.includes('challenge') || m.includes('counter') || m.includes('wrong') || m.includes('hinterfrag') || m.includes('gegenargument') || m.includes('falsch')) return { text: 'Strongest counter-argument: the premium is certain while an interruption is not. At a one-in-ten-years chance, the expected loss is about €21M per year, roughly equal to the €19M premium. The recommendation holds mainly because the guideline requires two sources.', cites: [3, 9] };
  if (m.includes('risk') || m.includes('risik')) return { text: 'Five risks were rated. Qualification failure (R1) and quality divergence (R4) rate high. Both fall back to Supplier A volume under a contract extension.', cites: [4, 8] };
  if (m.includes('cost') || m.includes('price') || m.includes('premium') || m.includes('kosten') || m.includes('preis') || m.includes('prämie')) return { text: 'Option 2 costs €69.6 per kWh against €69.0 for single sourcing, a premium of €0.6 per kWh or about €19M per year at 32 GWh.', cites: [1, 2, 3] };
  return { text: 'I can answer from the 10 sources in this analysis. Ask about cost, risks or timeline, or tell me what to change in a section.', cites: [] };
}

export const RUN_STEPS = [
  { id: 'read', title: 'Reading your material', agent: 'Reader', finding: 'Read 6 files, 1 email thread and 1 chat export' },
  { id: 'extract', title: 'Extracting figures and images', agent: 'Extractor', finding: '3 charts and 2 tables found for reuse in the report' },
  { id: 'internal', title: 'Searching Confluence, Jira and Wiki', agent: 'Researcher', finding: '3 internal pages matched, including the supplier guideline' },
  { id: 'web', title: 'Checking public sources', agent: 'Web researcher', finding: '1 public price outlook used' },
  { id: 'analyse', title: 'Comparing options and building charts', agent: 'Analyst', finding: '3 options compared, 5 charts built' },
  { id: 'check', title: 'Cross-checking every figure', agent: 'Cross-checker', finding: 'Conflict: qualification cost is €14.2M in the email, €15.1M in the cost model', warn: true },
  { id: 'challenge', title: 'Challenging the recommendation', agent: 'Challenger', finding: '4 questions the committee is likely to ask' },
  { id: 'map', title: 'Mapping to the committee template', agent: 'Template mapper', finding: '7 sections ready for your review' },
];

// -------------------------------- Slides -----------------------------------
export function buildSlides(sections, ctx) {
  // sections: ordered, included ones only (already edited by the user)
  const { qc, title, committee, date, version, prev = [] } = ctx;
  const find = (id) => sections.find((s) => s.id === id);
  const prevById = Object.fromEntries(prev.map((s) => [s.id, s]));
  const slides = [{ id: 'sl-title', layout: 'title', title, meta: { committee, date, version }, bullets: [], notes: null, qcv: qc, sources: [], sectionId: null }];
  const mk = (id, layout, section, extra = {}) => {
    // Raw text (with {n} / %QC% tokens) is stored; <Slide> translates and fills it at render time so the language toggle works.
    const bullets = section.bullets.slice();
    const old = prevById[id];
    return {
      id, layout, sectionId: section.id,
      title: section.headline,
      bullets,
      decision: section.decision || null,
      qcv: qc,
      notes: old ? old.notes : null,
      sources: section.sources,
      ...extra,
    };
  };
  const s1 = find('s1'); if (s1) slides.push(mk('sl-s1', 'summary', s1));
  const s2 = find('s2'); if (s2) slides.push(mk('sl-s2', 'text', s2));
  const s3 = find('s3'); if (s3) slides.push(mk('sl-s3', 'capacity', s3));
  const s4 = find('s4');
  if (s4) {
    slides.push({ ...mk('sl-s4a', 'table', s4), bullets: [] });
    slides.push({ ...mk('sl-s4b', 'charts', s4), title: 'Option 2 stays within €0.6 per kWh of single sourcing while prices fall about 2% per year' });
  }
  const s5 = find('s5'); if (s5) slides.push(mk('sl-s5', 'risk', s5));
  const s6 = find('s6'); if (s6) slides.push(mk('sl-s6', 'timeline', s6));
  const s7 = find('s7'); if (s7) slides.push(mk('sl-s7', 'text', s7));
  return slides;
}

// ------------------------------- Versions ----------------------------------
export const VERSION_HISTORY = [
  {
    id: 'v1', status: 'Presented', date: '05.11.2026', committee: 'FAKOM', by: 'Katrin Weber',
    feedback: [
      { text: 'Show a cost sensitivity for different volume splits', where: 'Options and cost' },
      { text: 'Add Supplier B capacity beyond 2027', where: 'Supplier landscape' },
      { text: 'Clarify when the volume split can be changed', where: 'Recommendation' },
    ],
  },
];
export const VERSION_DIFF = [
  { section: 'Options and cost', kind: 'Added', before: 'Cost comparison of three options.', after: 'Cost comparison plus sensitivity for 50/50 and 70/30 splits.' },
  { section: 'Supplier landscape', kind: 'Changed', before: 'Capacity stated to 2027.', after: 'Capacity stated to 2029; gap beyond 2029 flagged.' },
  { section: 'Recommendation and next steps', kind: 'Changed', before: 'Approve option 2.', after: 'Approve option 2 and review the split after 12 months.' },
];

// ----------------------------- Presenter notes -----------------------------
export const DESIGN_NOTES = {
  home: {
    title: 'Why the start is one field',
    points: [
      'Starting a report is one sentence or one tap, never a form. Effort before the first reward is where tools lose people.',
      'Deadlines lead: upcoming committees come from the calendar, so the context is already there.',
      'Reports, versions and teammates are visible at once. A chat history cannot show that.',
    ],
  },
  1: {
    title: 'Brief: speak first, correct later',
    points: [
      'Voice first. A spoken brief takes 30 seconds. The assistant fills topic, committee, date and template while you talk; you only correct.',
      'No interview. Three optional questions, one tap each, that refer to what it found (“I saw last year’s FAKOM report”). Skipping costs nothing.',
      'Brief strength shows what more input buys, and never blocks. People like to see progress and keep control.',
      'Material shows what was extracted (charts, tables, slides), so effort is visible before analysis starts.',
    ],
    beyond: ['Structured outline from your own template, editable before anything is written', 'Sources and connectors chosen explicitly, not pasted blindly', 'You can return here at any time'],
  },
  2: {
    title: 'Analysis: depth you can inspect',
    points: [
      'The complexity is shown as a calm summary: agents, sources, cross-checks. It signals depth without asking anything of the user.',
      'Every claim carries a source. Click a number to see the passage. Conflicts and gaps are flagged, not smoothed over.',
      'Review per section: approve, edit, redo with an instruction, or leave out. The user always holds the pen.',
      'Challenger and committee questions prepare you for the meeting. A general chat does not do this unprompted.',
    ],
    beyond: ['Change the brief and only affected sections refresh', 'Conflicts resolved once, reflected on every slide', 'Open items visible before they turn into committee questions'],
  },
  3: {
    title: 'Report: the committee template, linked to the analysis',
    points: [
      'Slides follow the committee template. Edit text directly; every slide still points to its section and sources.',
      'Checks catch inconsistencies before the committee does, for example an open conflict in the analysis.',
      'Versions and committee feedback live next to the report. Version 2 starts from what the committee asked for.',
      'Colleagues can comment, review or edit the same report.',
    ],
    beyond: ['Analysis and slides stay in sync, with “update slides” instead of copy and paste', 'Version history with comparison', 'Review workflow with named reviewers'],
  },
};
