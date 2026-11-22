# VW branding instructions (colours and fonts only)

Audience: GitHub Copilot, or any LLM coding assistant, working in this repository.
Goal: make the prototype use the Volkswagen Group UI colours and typography. Nothing else changes.

**Where things are:** this file lives in the front-end folder `committee-report-assistant/`. Every path below (`src/styles.css`, `index.html`, ...)
and every command in section 5 is relative to that folder, not to the repository root. Do `cd committee-report-assistant` first.
`git diff --stat` shows the same files with the prefix `committee-report-assistant/`. The overall project is described in `COPILOT_START_HERE.md` (repository root, Task 3).

## 1. Inputs (fill these in before starting)

| What | URL or location |
|---|---|
| Group UI / design system (main entry) | `PASTE URL HERE` |
| Colour palette and tokens | `PASTE URL HERE` |
| Typography and font files (or how to load them) | `PASTE URL HERE` |
| Logo and brand-mark usage (optional) | `PASTE URL HERE` |

Read these pages first. If a value is missing or unclear, do not guess. Write the question into section 8 and keep the current value.

## 2. Scope: what may and may not change

May change:
- Colour values and font families, and only through the tokens listed in section 3.
- The font loading in `index.html` (the Google Fonts `<link>` tags), plus font files you add for self-hosting.
- `font-size`, `letter-spacing` and `line-height` of the `.display` classes, and only if the new font looks wrong at the current values.

Must not change:
- Layout, spacing, border radius, shadows (their structure), borders, component structure, JSX, class names, copy text, behaviour, animations, data, routing or dependencies.
- Button shapes and sizes. They are fine as they are.
- Token names. Only change token values.

If the design system prescribes something outside this scope (radius, button style, spacing, iconography), do not apply it. Add one line to section 8 instead.

## 3. Where the tokens live

All colours are defined once, in the `:root` block at the top of `src/styles.css`. No hex colour is hard-coded anywhere else, except `#fff` (white) and `rgba(255,255,255,x)` overlays in `styles.css`.

| Token | Role in the UI | Notes |
|---|---|---|
| `--ink`, `--ink-rgb` | Primary text, dark surfaces (logo, slide cover, notes card, toasts, dark buttons) | Keep `--ink-rgb` equal to `--ink` as `r, g, b` |
| `--ink-2`, `--ink-3` | Secondary and muted text | `--ink-3` must keep 4.5:1 contrast on white |
| `--bg`, `--surface`, `--sunken`, `--surface-2/3/4` | App background, cards, subtle fills | |
| `--line`, `--line-strong` | Hairlines and input borders | |
| `--accent`, `--accent-ink`, `--accent-soft`, `--accent-rgb` | Primary buttons, links, focus, selected state, hover | White text on `--accent` must keep 4.5:1. Keep `--accent-rgb` equal to `--accent` |
| `--accent-line`, `--accent-line-2` | Borders on accent-soft surfaces | |
| `--accent-on-dark`, `--on-dark-1`, `--on-dark-2` | Accent and text colours on dark surfaces | |
| `--good`, `--good-soft`, `--good-line`, `--good-line-2`, `--good-ink`, `--good-on-dark` | Success and reviewed state | Status colours stay reserved for status |
| `--warn`, `--warn-soft`, `--warn-line`, `--warn-line-2` | Open items, conflicts, warnings | |
| `--crit`, `--crit-rgb`, `--crit-soft`, `--crit-ink` | Recording state, errors, removed text in comparisons | |
| `--risk-high/-med/-low` and `-ink` | Risk matrix and risk labels | Keep three clearly different levels, with a text label on each |
| `--chart-1`, `--chart-2` | Chart series 1 and 2 | Must stay clearly distinguishable from each other, also for colour-blind users |
| `--chart-muted`, `--chart-neutral` | Reference lines, non-highlighted bars | |
| `--avatar-1/2/3` | Avatar backgrounds | White initials must stay readable |
| `--skeleton-1/2`, `--present-bg` | Loading placeholders, full-screen presentation background | |

Fonts:

| Token | Used for | Currently |
|---|---|---|
| `--f-sans` | All body text, UI, slides, charts | Geist |
| `--f-serif` | Large display text: page headlines, section headlines, big numbers, slide cover title | Instrument Serif (regular and italic) |
| `--f-mono` | Small technical labels (source numbers, step numbers) | Geist Mono |

Font loading is in `index.html` (Google Fonts link). The font stacks are in the `:root` block of `src/styles.css`.

## 4. Steps

1. Read the URLs in section 1. Write down the official values: primary, secondary and neutral colours, status colours, chart or data colours if given, the display font and the text font, and any weights.
2. Map each official colour to the closest role in the token table. Brand colours go to `--ink`, `--accent` and their variants. Neutrals go to `--bg`, `--surface`, `--line`, `--ink-2`, `--ink-3`. Derive tints (`-soft`, `-line`) from the same hue. Keep `--*-rgb` tokens in sync.
3. Update only the values in the `:root` block of `src/styles.css`.
4. Fonts:
   - Replace the Google Fonts link in `index.html` with the font loading the design system specifies (self-hosted `@font-face` files, a CDN stylesheet, or the corporate font package). Do not invent font file URLs.
   - Set `--f-sans` to the official text font and `--f-serif` to the official display font. Keep a fallback stack after the official name.
   - If the display font has no italic, add `font-style: normal;` to `.display em` and keep its accent colour as the emphasis.
   - If the design system has one family only, set `--f-serif` to the same family as `--f-sans`.
   - Do not hard-code font names anywhere except these tokens. `src/components/Charts.jsx` already reads `--f-sans`.
5. If the official brand colour is dark, check every place that puts white text on `--ink` or `--accent`: primary buttons, dark buttons, slide cover, toasts, notes card. Adjust the token, not the components.
6. The logo mark in the top bar (`.brand-mark` in `src/styles.css`, rendered by `src/components/TopBar.jsx`) is a neutral placeholder, not a brand logo. Replace it with the official logo only if the design system provides the asset and usage rules. Otherwise leave it.
7. Run the checks in section 5. Fix findings by changing token values.

## 5. Checks before finishing

Run from the front-end folder `committee-report-assistant/`.

```
npm install
npm run build
```

Then check that no colour is hard-coded outside the `:root` block (this should list nothing except `#fff`):

```
# bash / Git Bash
awk '/^\*, \*::before/{f=1} f' src/styles.css | grep -nE "#[0-9A-Fa-f]{3,8}\b" | grep -v "#fff"
grep -rnE "#[0-9A-Fa-f]{6}\b" src --include=*.jsx --include=*.js

# PowerShell
Select-String -Path src\components\*.jsx,src\*.js -Pattern "#[0-9A-Fa-f]{6}\b"
```

Check the diff:

```
git diff --stat
```

Only these files may appear: `src/styles.css`, `index.html`, `VW_BRANDING.md`, and any font files you added. If anything else changed, revert it and use the tokens instead.

Look at the running app (`npm run dev`) and compare with the previous look:
- Home, then all three stages: Brief, Analysis, Report.
- Slides in the Report stage, including the cover slide and the Present view.
- Every chart type: cost bars, price lines, capacity bars, risk matrix, timeline.
- States: hover and focus on buttons, selected chips, warning and conflict boxes, the recording state of the Speak button, toasts, the Versions drawer.
- Contrast: body text 4.5:1, large text 3:1, white text on accent and ink backgrounds 4.5:1.
- Layout identical to before: nothing moved, wrapped differently or got clipped. A different font can change text width, so check long headlines and the stepper in the top bar.

## 6. Ready-to-paste prompt for Copilot

```
Read VW_BRANDING.md in this repository and follow it exactly.
Use the URLs listed in section 1 as the only source of truth for colours and fonts.
Change only token values in the :root block of src/styles.css and the font loading in index.html.
Do not change layout, components, copy or behaviour, and do not add dependencies.
When done, run the checks in section 5, then fill in section 8 with what you changed,
what you could not determine, and any design-system rules that were out of scope.
```

## 7. Definition of done

- The app uses the official colours and fonts everywhere, through the tokens.
- `npm run build` passes and the hard-coded colour check lists nothing.
- The diff touches only the files allowed in section 5.
- Contrast and chart distinguishability checks pass.
- Section 8 is filled in.

## 8. Change log and open questions (Copilot fills this in)

Changed:
- (none yet)

Open questions or values that could not be determined:
- (none yet)

Design-system rules outside this scope (not applied):
- (none yet)
