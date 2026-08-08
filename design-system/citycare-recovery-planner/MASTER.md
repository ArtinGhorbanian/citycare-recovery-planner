# CityCare Recovery Planner design system

**Status:** implemented release system

**Updated:** 2026-08-08

**Product type:** data-dense operational decision-support dashboard
**Design dials:** moderate visual variance, subtle motion, high information density

## Product principles

1. Keep hospital, scenario time, data basis, and result freshness visible across workflows.
2. Treat loading, draft, current, stale, locked, degraded, and error conditions as first-class states.
3. Pair every chart with accessible data and preserve the workflow when chart rendering fails.
4. Use calm, restrained visual hierarchy; color communicates state but never carries meaning alone.
5. Keep clinical and operational claims conservative: this is a prototype, not a live or medical system.
6. Prefer local assets and system fonts so the core interface has no third-party browser requests.

## Implemented palette

The canonical tokens live in `static/style.css`.

| Role | Token | Value |
| --- | --- | --- |
| Primary navigation | `--navy-900` | `#0b2238` |
| Primary action | `--teal-600` | `#0f7f8c` |
| Dark teal text/action | `--teal-700` | `#0b6b76` |
| Light teal surface | `--teal-100` | `#e2f5f7` |
| Positive state | `--green-600` | `#1c7a4b` |
| Caution state | `--amber-600` | `#835000` |
| Critical state | `--red-600` | `#b1281f` |
| Strong text | `--text-strong` | `#0f1f2e` |
| Body text | `--text-body` | `#35485c` |
| Muted text | `--text-muted` | `#52687c` |
| App background | `--background` | `#f3f6fa` |
| Surface | `--surface` | `#ffffff` |

All normal-size text targets at least WCAG AA contrast. The small uppercase `.view-step` label uses `--teal-700` against the app background.

## Typography

- Font stack: system UI (`-apple-system`, BlinkMacSystemFont, `Segoe UI`, sans-serif).
- No remote font import.
- Body size: 16 px on narrow screens to prevent mobile form zoom.
- Headings use a compact 1.25 line height; body copy uses 1.6.
- Labels and status metadata may use uppercase and tracking only at accessible sizes and contrast.

## Layout

- Desktop: fixed 272 px navigation rail plus a fluid content canvas.
- Content: constrained, centered dashboard sections with dense cards and tables.
- Scenario strip: persistent summary of hospital, time, basis, and freshness.
- Mobile: off-canvas navigation, single-column fields/cards, safe-area padding, and no horizontal page overflow.
- Touch targets: at least 44 px for interactive controls on narrow screens.

## Components and states

### Navigation

- Each workflow item includes a title, short purpose, SVG icon, and optional state text.
- Result sections expose `Locked`, `Ready`, or `Stale` in text as well as color.
- Mobile drawer moves focus to Close, traps focus, closes on Escape, marks background content inert, and restores focus to the opener.

### Forms

- Labels are explicit and helper text explains units.
- Inline errors use `aria-invalid`, field-level messages, and a summary that focuses the first invalid control.
- Required hospital prefills lock the whole scenario fieldset; manual latest-load requests can be canceled safely by a newer edit.

### Results

- Provenance panels show hospital, scenario time, received time, and data basis.
- Any upstream edit invalidates dependent prediction/allocation output and disables stale downloads.
- Capacity and risk states combine plain language, numbers, and restrained semantic color.

### Charts and tables

- Chart.js 4.4.1 is self-hosted and loaded as a nonblocking enhancement.
- Canvas elements have useful accessible names.
- Equivalent table data is available through disclosure controls.
- When the library is missing or rendering fails, the table remains usable and a plain-language notice appears.

## Motion

- Motion is limited to short hover, focus, drawer, and scrolling transitions.
- `prefers-reduced-motion: reduce` disables smooth scrolling, chart animation, and nonessential transitions.
- No scroll-reveal library, parallax, autoplay, or attention-seeking animation is used.

## Content rules

- Say “configured dataset,” “dataset records,” or “training/test set”; do not claim unverified real-world provenance.
- Label the repository demo data as synthetic and non-representative.
- Never present model estimates as verified resources, causal explanations, clinical decisions, or guaranteed outcomes.
- State AI mode accurately: fixed-rule is the default; invalid or unavailable AI configuration is a degraded fixed-rule state.
- Keep the competition reference descriptive and make no endorsement, award, or ownership claim.

## Release checklist

- Keyboard-only navigation and visible focus verified.
- Drawer focus trap, Escape close, background inertness, and focus restoration verified.
- 375 px mobile layout has no page-level horizontal overflow.
- Form inputs remain at least 16 px on mobile and controls meet the 44 px target.
- Stale result and download invalidation verified.
- Reduced-motion behavior present.
- Charts have table equivalents and graceful failure behavior.
- Lighthouse/axe contrast findings reviewed; local favicon prevents avoidable console errors.
