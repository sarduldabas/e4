// Client for every backend endpoint the live screens use. One small function per endpoint, no state.
const BASE = (import.meta.env?.VITE_API_URL ?? 'http://localhost:8001').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function detailOf(body, status) {
  const d = body?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ');
  return `HTTP ${status}`;
}

async function call(method, path, { json, form, signal, blob } = {}) {
  const init = { method, signal, headers: {} };
  if (json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(json); }
  if (form) init.body = form;
  let res;
  try { res = await fetch(`${BASE}${path}`, init); } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, 'backend unreachable');
  }
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(res.status, detailOf(body, res.status));
  }
  if (res.status === 204) return null;
  return blob ? res.blob() : res.json();
}

const R = (rid) => `/api/v1/reports/${rid}`;
const get = (p, o) => call('GET', p, o);
const post = (p, json, o) => call('POST', p, { json, ...o });
const put = (p, json, o) => call('PUT', p, { json, ...o });
const patch = (p, json, o) => call('PATCH', p, { json, ...o });
const del = (p) => call('DELETE', p);

export const api = {
  base: BASE,
  // system
  status: (signal) => get('/api/v1/system/status', { signal }),
  layouts: () => get('/api/v1/slide-layouts'),
  committees: () => get('/api/v1/committees'),
  // reports
  reports: () => get('/api/v1/reports'),
  createReport: (title, committee_id) => post('/api/v1/reports', { title, committee_id: committee_id || null }),
  deleteReport: (rid) => del(`/api/v1/reports/${rid}`),
  assess: (payload, signal) => post('/api/v1/brief/assess', payload, { signal }),
  // case, files
  case: (rid, signal) => get(`${R(rid)}/case`, { signal }),
  putCase: (rid, body) => put(`${R(rid)}/case`, body),
  files: (rid) => get(`${R(rid)}/files`),
  upload: (rid, file, role = 'source') => { const f = new FormData(); f.append('file', file); f.append('role', role); return call('POST', `${R(rid)}/files`, { form: f }); },
  deleteFile: (rid, fid) => del(`${R(rid)}/files/${fid}`),
  sources: (rid) => get(`${R(rid)}/sources`),
  researchPlan: (rid) => get(`${R(rid)}/research-plan`),
  assets: (rid) => get(`${R(rid)}/assets`),
  patchAsset: (rid, id, body) => patch(`${R(rid)}/assets/${id}`, body),
  // brief
  proposeOutline: (rid) => post(`${R(rid)}/outline/propose`),
  outline: (rid) => get(`${R(rid)}/outline`),
  putOutline: (rid, sections) => put(`${R(rid)}/outline`, sections),
  interview: (rid) => get(`${R(rid)}/interview`),
  turn: (rid, text, done = false) => post(`${R(rid)}/interview/turn`, { text, done }),
  approveOutline: (rid) => post(`${R(rid)}/outline/approve`),
  rerun: (rid, sections) => post(`${R(rid)}/research/rerun`, sections ? { sections } : {}),
  // the evidence behind the draft
  findings: (rid) => get(`${R(rid)}/findings`),
  patchClaim: (rid, id, body) => patch(`${R(rid)}/claims/${id}`, body),
  resolveFlag: (rid, id, resolution, note) => post(`${R(rid)}/flags/${id}/resolve`, { resolution, note }),
  includeClaim: (rid, id) => post(`${R(rid)}/claims/${id}/include`),
  buildDeck: (rid) => post(`${R(rid)}/deck/build`),
  // the draft
  deck: (rid) => get(`${R(rid)}/deck`),
  patchSlide: (rid, id, spec) => patch(`${R(rid)}/deck/slides/${id}`, { spec }),
  addSlide: (rid, after, layout) => post(`${R(rid)}/deck/slides`, { after, layout }),
  reviseSlide: (rid, id, instruction) => post(`${R(rid)}/deck/slides/${id}/revise`, { instruction }),
  undoSlide: (rid, id) => post(`${R(rid)}/deck/slides/${id}/undo`),
  moveSlide: (rid, id, index) => put(`${R(rid)}/deck/slides/${id}/position`, { index }),
  deleteSlide: (rid, id) => del(`${R(rid)}/deck/slides/${id}`),
  ask: (rid, body) => post(`${R(rid)}/deck/ask`, body),
  undoAsk: (rid) => post(`${R(rid)}/deck/ask/undo`),
  downloadDeck: async (rid) => {
    const res = await fetch(`${BASE}${R(rid)}/deck/download`);
    if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'report.pptx';
    return { name, blob: await res.blob() };
  },
  assetUrl: (rid, id) => `${BASE}${R(rid)}/assets/${id}`,
  // audit
  events: (rid) => get(`${R(rid)}/events`),
  runs: (rid, io = false) => get(`${R(rid)}/agent-runs${io ? '?io=true' : ''}`),
  runSummary: (rid) => get(`${R(rid)}/agent-runs/summary`),
};

/** Saves a Blob as a file in the browser. */
export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
