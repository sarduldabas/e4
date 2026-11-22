// Client for the backend (FastAPI). The prototype keeps working without it: when the backend or the agents
// are not reachable, the front end falls back to its built-in local logic.
const BASE = (import.meta.env?.VITE_API_URL ?? 'http://localhost:8001').replace(/\/$/, '');
const TIMEOUT_MS = 3000;
const RETRY_AFTER_MS = 15000;
let downUntil = 0; // after a failure, skip the network for a while so the UI does not wait on every keystroke

async function post(path, body, signal) {
  if (Date.now() < downUntil) throw new Error('backend offline');
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, TIMEOUT_MS);
  const onAbort = () => ctrl.abort();
  signal?.addEventListener('abort', onAbort);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    if (!signal?.aborted) downUntil = Date.now() + RETRY_AFTER_MS; // real failure or timeout, not a cancelled request
    if (timedOut) throw new Error('backend timeout');
    throw e;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/** What the Brief agent needs to see. Mirrors BriefAssessRequest in backend/app/schemas.py. */
export function briefPayload(brief, lang) {
  return {
    lang,
    text: brief.text || '',
    overrides: brief.overrides || {},
    preset_committee: brief.presetCommittee || null,
    files: brief.files.map((f) => ({ name: f.name, kind: f.kind || null, status: f.status === 'ready' ? 'ready' : 'reading' })),
    links: brief.links.map((l) => l.url),
    connectors: brief.connectors || {},
    answers: brief.answers || {},
  };
}

export const assessBrief = (payload, signal) => post('/api/v1/brief/assess', payload, signal);
