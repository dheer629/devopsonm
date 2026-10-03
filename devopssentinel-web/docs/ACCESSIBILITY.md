# Accessibility Report

Target: WCAG 2.2 AA as a floor, with AAA practices where practical.

## Automated results

Run with `@axe-core/playwright` against the production build, tags
`wcag2a, wcag2aa, wcag21a, wcag21aa`, in **both dark and light** colour schemes:

| Route | dark | light |
| --- | --- | --- |
| `/dashboard` | ✅ 0 serious/critical | ✅ |
| `/workloads` | ✅ | ✅ |
| `/findings` | ✅ | ✅ |
| `/pki` | ✅ | ✅ |
| `/gitops` | ✅ | ✅ |
| `/settings` | ✅ | ✅ |
| `/doctor` | ✅ | ✅ |

Reproduce:

```bash
cd frontend && npx playwright test e2e/a11y.spec.ts
```

A defect found by this suite and fixed during development: the LIVE-refresh `Select` trigger in the
top bar had no accessible name (`button-name`, critical). All `Select` triggers now carry an
explicit `aria-label`.

## Practices implemented

| Requirement | Implementation |
| --- | --- |
| Keyboard operation | Every control is a native button/input/select or a Radix primitive with full keyboard support |
| Visible focus | Global `*:focus-visible` outline in the accent colour |
| No keyboard traps | Radix dialogs/popovers restore focus on close; Escape closes drawers and the palette |
| Semantic structure | `h1` per page, `nav[aria-label]`, `aside[aria-label]`, `footer`, real `<table>` with `<th scope="col">` |
| Table semantics | `aria-sort` on sortable headers; `role="region"` + label on the scroll container |
| Screen-reader labels | Icon-only buttons use `aria-label`; selects use `aria-label`; decorative icons use `aria-hidden` |
| Colour independence | Status is always **glyph + text + colour** (`● Healthy`, `▲ Warning`, `✕ Critical`, `? Unknown`) |
| Live regions | `role="status"` on the PARTIAL banner; `role="alert"` on error states |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` neutralises transitions and animation |
| Zoom | Layout is fluid from 1280 px to 2560 px; no fixed-height clipping; 200% zoom supported |
| Target size | Primary controls are ≥ 28 px with 44 px-friendly spacing on touch-capable layouts |
| Contrast | Semantic tokens tuned so muted/faint text exceeds 4.5:1 on panel backgrounds in both themes |

## Manual verification checklist

- [x] Tab through the shell reaches nav → workspace → inspector → status bar in logical order
- [x] `Ctrl/Cmd+K` and `/` open the command palette; arrow keys move; Enter navigates; Escape closes
- [x] `g d`, `g p`, `g g`, `g c`, `g n`, `g s`, `g f`, `g t`, `g e` chords navigate
- [x] Drawer/inspector close button is keyboard reachable and labelled
- [x] Error state exposes reason / impact / next safe action and hides raw detail behind a disclosure
- [x] Empty, unavailable, failed and partial states are all distinguishable by text alone

## Known gaps

* No formal screen-reader (NVDA/JAWS/VoiceOver) session has been recorded yet.
* `aria-live` announcements are limited to the partial-data banner and error states; a dedicated
  live region for table row-count changes would be an improvement.
* The React Flow canvas is operable by keyboard only for pan/zoom controls; individual node
  navigation is pointer-driven, with an equivalent text edge list provided below the graph.
