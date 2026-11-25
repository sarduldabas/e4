# Committee Report Assistant: front-end prototype (COE4)

React 18 + Vite. Mock content lives in `src/data.js`. Stage 1 (Brief) talks to the backend service when it is running
and falls back to local logic when it is not, so the prototype also works as a standalone file. See `../README.md` for the three-service setup.

```
npm install
npm run dev      # development
npm run build    # single self-contained dist/index.html
```

Structure
- `src/App.jsx`: state, stage navigation, change propagation (brief -> analysis -> slides)
- `src/components/StageBrief.jsx`, `StageAnalysis.jsx`, `StageReport.jsx`: the three stages
- `src/components/Charts.jsx`, `Slide.jsx`: SVG charts and the 960x540 slide renderer
- `src/components/Overlays.jsx`: versions drawer, share dialog, design notes (demo layer)
- `src/workspace.js`: workspace state, smart-chip detection, brief strength
- `src/styles.css`: design tokens and all styles (colors, type scale at the top)

Where the backend plugs in (search for these)
- Voice: `startVoice` in `StageBrief.jsx` uses the browser's own speech input (Web Speech API, Chrome/Edge). See "Backend and speech" below.
- File extraction: `addReal` / `addSample` in `StageBrief.jsx`.
- Analysis run: `RunView` in `StageAnalysis.jsx` (timer now; later stream agent events).
- Section content and citations: `SECTIONS` and `SOURCES` in `data.js`.
- Slide generation: `buildSlides` in `data.js`. PPTX export is mocked in `StageReport.jsx`.

Branding
- `VW_BRANDING.md` explains how to switch to the VW Group colours and fonts without touching anything else.
  Give Copilot the Group UI URL in the chat (Task 3 in `../COPILOT_START_HERE.md`) or fill in section 1 yourself; the prompt is in section 6.
  All paths and commands in that file are relative to this folder.

Language (German default, English switchable)
- The UI opens in German. The DE | EN toggle sits at the top right of the nav bar (`LangToggle` in `TopBar.jsx`).
  State lives in `App.jsx` (`lang`); it is not persisted, so every start begins in German.
- All strings go through `t('English text')` from `src/i18n.js`. The German text lives in `src/i18n.de.js`, keyed by the English string.
  A string without an entry shows in English, so nothing breaks. Placeholders: `t('Slide {n} of {total}', { n, total })`.
  Keep `{n}` citation markers and `%QC%` exactly as in the key.
- Mock content in `data.js` stays in English; it is translated at render time, so the toggle switches everything live,
  including generated slides. Numbers use a decimal comma in German (`num()` in `i18n.js`, `qcText()` in `data.js`).
- To find untranslated strings: open the app in German, click through, then run `[...window.__i18nMissing]` in the browser console.
- Register is formal (Sie). Have a native speaker review the wording before user tests.
- New UI text: wrap in `t()` and add the German line. Do not translate by editing the English strings.

Backend and speech
- `src/api.js` is the only file that calls the backend. Base URL: `VITE_API_URL` (default `http://localhost:8001`, see `.env.example`).
- Stage 1 sends the brief (text, files, links, sources, answers, language) to `POST /api/v1/brief/assess` after 400 ms of quiet.
  The request is sent after 800 ms of quiet. The backend asks the Brief agent (language model if configured, else rules) and returns the score, 2-3 line summary, hints and up to 3 questions. The two Stage 1 cards show that answer.
- Offline fallback: if the backend or agent does not answer within 25 s (the agent may be calling a language model), the cards use the local logic (`briefStrength`, `BRIEF_QUESTIONS`)
  and the front end retries after 15 s. The "Assessed by the brief agent" line only shows when the agent answered.
- Answers to the three questions are stored as option ids (`approve`, `yes`, `align`, ...), not as display text, so they are the same in German and English.
- Speech: "Sprechen / Speak" starts `SpeechRecognition` (language de-DE or en-US), shows live text while you talk and restarts itself
  after pauses until you click again. Unsupported browsers and a blocked microphone show a message.
  Note: Chrome sends the audio to Google's speech service. That conflicts with "stays in the Volkswagen environment".
  Replace it with Azure Speech inside the VW tenant before real users or real data (the change is local to `startVoice`).

## Demo and Live mode

The top bar has a **Demo | Live** switch (remembered in the browser).

- **Demo**: the built-in sample data (`src/data.js`, `src/workspace.js`); nothing is sent anywhere. Only the brief score calls the backend when it runs.
- **Live**: everything runs on the backend (`src/live/`): `LiveApp.jsx` (reports), `LiveBrief.jsx` (brief, files with reading quality, outline, interview),
  `LiveAnalysis.jsx` (progress, claims, evidence, flags, sources), `LiveReport.jsx` + `SlideCanvas.jsx` (slides drawn from the same JSON as the PowerPoint file,
  editable on the slide, per-slide comments to the slide editor, undo, add/move/delete, download), `LiveAudit.jsx` (the **Agent log** tab, Live only).
  `client.js` has one function per backend endpoint. The slide geometry and theme come from `GET /api/v1/slide-layouts`, so the page and the file cannot drift apart.
  The backend URL is `VITE_API_URL` (default `http://localhost:8001`).

Live mode shows a banner when the backend or the agents service is down, or when the agents run without a language model (rules mode).
