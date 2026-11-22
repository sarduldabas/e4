
## Language (added 23.11.2026)
- German is the default UI language; DE | EN toggle at the top right of the nav bar. Everything else unchanged.
- Implementation: `src/i18n.js` (`t`, `num`), `src/i18n.de.js` (about 620 German strings, formal Sie). Details in README, section "Language".
- Slides, charts, sample content and chat replies switch live. Typed text stays as typed.
- Open: native-speaker review of the German wording (VW terminology, e.g. Gremium, Review-Gate, Lastenheft-style terms) before sample-user tests.
- Open: the demo language is not remembered between sessions (always starts in German). Add persistence if wanted.

## Three services (backend + agents added)
- Layout: `committee-report-assistant/` (front end, 5173), `backend/` (FastAPI, 8001), `agents/` (FastAPI, 8002). Start: `.\start-all.ps1 -Install` once, then `.\start-all.ps1`. Details in `README.md`.
- Wired: Stage 1 Brief. Front end -> backend `/api/v1/brief/assess` -> Brief agent (rule-based) returns score, 2-3 line summary, hints, up to 3 optional questions. Offline fallback to local logic if services are down.
- Speak button uses the browser speech input (Chrome/Edge). Open: Chrome sends audio to Google, so replace with Azure Speech inside the VW tenant before real data.
- Ready in backend, not yet used by front end: committees, reports CRUD, workspace autosave (JSON store, DB later).
- Next: wire Analysis (Stage 2) agents (reader, extractor, researcher, analyst, cross-checker, challenger), LLM version of the Brief agent, Azure Speech, DB + login, slide builder (Stage 3).
