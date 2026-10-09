# Verelo design system

**For the coding agent:** this folder is the source of truth for how Verelo looks. Read this whole file before writing UI code. Use only the tokens, fonts and logo files in this folder. Do not invent new colors, fonts, shadows or radii. If something you need isn't covered, pick the closest existing token and leave a `TODO(design):` comment.

## What Verelo is

Verelo is an internal tool for a consulting firm. It records expert calls, saves the transcripts, finds verified, word-for-word quotes across a project, has a chatbot that helps find quotes, and groups primary research into projects. The look should be **simple, streamlined and modern**: quiet neutral surfaces, navy text, one teal accent, and nothing that competes with transcript text. Trust and exactness matter more than flair.

## Folder contents

| Path | What it is |
| --- | --- |
| `tokens/tokens.css` | **Import this first.** CSS variables for both themes, `@font-face` rules, `.text-*` type classes and base styles. |
| `tokens/tailwind.preset.js` | Tailwind 3 preset that maps every token to its CSS variable (`bg-surface`, `text-ink-muted`, `rounded-lg`, `text-body`, `font-serif`). |
| `tokens/tokens.json` | The same tokens as data, with a usage note on every token. |
| `fonts/` | Self-hosted variable `.woff2` files, plus their SIL Open Font License texts in `fonts/licenses/`. Don't load fonts from Google. |
| `logos/` | Transparent PNG logos (see Logo). |
| `preview.html` | Open in a browser to see every token, type style, component and logo, in light and dark. |

## Setup

1. Copy this folder into the project, e.g. `src/design/verelo-design-system/`. Keep `tokens/` and `fonts/` side by side; `tokens.css` loads fonts from `../fonts/`.
2. Import `tokens/tokens.css` once at the app root, before any other stylesheet.
3. If you use Tailwind, add the preset: `presets: [require('./verelo-design-system/tokens/tailwind.preset.js')]`.
4. **Theming:** light is the default. Dark mode follows the OS setting, or can be forced with `<html data-theme="dark">` (or `"light"`). Always style with variables (`var(--surface)`) or the Tailwind classes. Never hard-code hex values, and never write separate dark-mode colors; the variables already switch.

## Color

Every text pair named in a usage note passes WCAG AA (4.5:1) in both themes. Input borders pass 3:1.

| Variable | Light | Dark | Use |
| --- | --- | --- | --- |
| `--brand-navy` | `#0b1f33` | `#0b1f33` | Logo navy, exact. The mark, the wordmark and brand moments only; UI text uses `ink`. |
| `--brand-teal` | `#12a594` | `#12a594` | Logo teal, exact. The center bar of the mark. In the UI it appears as `accent`. |
| `--canvas` | `#f5f7f9` | `#08141f` | Page background behind panels and the project grid. |
| `--surface` | `#ffffff` | `#0f1f30` | Cards, tables, the chat panel and modals. Text: `ink`, `ink-muted`, `accent-text`. |
| `--surface-sunken` | `#edf1f4` | `#0b1926` | Sidebar, transcript side panel and table header rows. Text: `ink`, `ink-muted`. |
| `--brand-panel` | `#0b1f33` | `#173350` | Brand-colored panels: the sign-in side panel and the cover slab. White text and the reverse logos sit on it. Lighter than navy in dark mode so it stays visible. |
| `--on-brand-panel` | `#ffffff` | `#ffffff` | Text and marks on `brand-panel` (16.7:1 light, 12.9:1 dark). |
| `--border` | `#dce3e8` | `#1e3246` | Hairline dividers between rows and panels. Decorative only. |
| `--border-strong` | `#7b8a97` | `#62778b` | Input, select and checkbox outlines. At least 3:1 on `surface` and `canvas`. |
| `--ink` | `#0b1f33` | `#e9eef3` | Primary text on `canvas`, `surface`, `surface-sunken`, `accent-soft` and `highlight`. Also the focus ring (2px, solid). |
| `--ink-muted` | `#526375` | `#9caebf` | Secondary text: timestamps, expert titles, metadata. On `canvas`, `surface`, `surface-sunken`. |
| `--accent` | `#12a594` | `#12a594` | Brand teal fill: primary buttons, the active nav marker, the verified-quote badge. Text on it is `on-accent` (navy), never white. |
| `--accent-strong` | `#2bb9a7` | `#2bb9a7` | Hover and pressed state of `accent` fills. Text: `on-accent`. |
| `--accent-text` | `#0a7366` | `#3fcab8` | Teal as text: links, "Verified" labels, active tab labels. On `surface`, `canvas` and `accent-soft`. |
| `--accent-soft` | `#d9f1ed` | `#103a3d` | Selected table rows, active filters and the chat assistant bubble. Text: `ink` or `accent-text`. |
| `--on-accent` | `#0b1f33` | `#0b1f33` | Text and icons on `accent` and `accent-strong` fills (navy, 5.4:1). |
| `--highlight` | `#fbe7a1` | `#5a4813` | Background behind a found quote in the transcript panel. Text: `ink`. |
| `--recording` | `#c8322b` | `#f26b5e` | The live-recording dot and destructive actions (delete transcript, close project). As text, on `surface`. |
### Color rules

- **Layering:** `canvas` (page) → `surface` (cards, tables, chat, modals) → `surface-sunken` (sidebar, transcript panel, table headers). Separate layers with 1px `border` hairlines. **No drop shadows** except one overlay shadow for menus and modals: `0 8px 24px rgba(11, 31, 51, 0.12)`.
- **Text:** `ink` for primary, `ink-muted` for secondary. Never use opacity to fade text.
- **Teal:** `accent` is the logo teal, used as a *fill*. Text on it is always `on-accent` (navy). **White text on teal fails contrast, so never use it.** When teal is *text* (links, "Verified", active tab), use `accent-text`.
- Use teal sparingly. Give it to one primary action per screen, the active nav item, and verified badges. Everything else stays neutral.
- A teal fill on `canvas` is only 2.9:1, so it must never be the only signal. Teal buttons always carry their navy label.
- `brand-navy` and `brand-teal` are the exact logo colors. They're for brand moments (hero art, the app icon), not regular UI.
- `brand-panel` is a navy block for big brand areas (the sign-in side panel, the marketing hero band, the footer). Put `on-brand-panel` text and the **reverse** logo files on it.
- `highlight` (yellow) only means "this is the found quote" inside a transcript.
- `recording` (red) is only for the live-recording dot and destructive actions. Always pair it with a word ("Recording", "Delete").

## Typography

| Class / Tailwind | Font | Size / line | Weight | Use |
| --- | --- | --- | --- | --- |
| `.text-display` / `text-display` | Plus Jakarta Sans | 28 / 34, −0.02em | 700 | Page title, one per screen |
| `.text-title` / `text-title` | Plus Jakarta Sans | 20 / 28, −0.01em | 700 | Transcript, panel and card titles |
| `.text-heading` / `text-heading` | Plus Jakarta Sans | 15 / 22 | 600 | Section headings, table headers |
| `.text-body` / `text-body` | Plus Jakarta Sans | 14 / 21 | 400 | Default UI and transcript text |
| `.text-small` / `text-small` | Plus Jakarta Sans | 12 / 16 | 600 | Badges, metadata, helper text |
| `.text-quote` / `text-quote` | Newsreader (serif) | 17 / 26 | 400 | Verbatim expert quotes only |
| `.text-timestamp` / `text-timestamp` | Geist Mono | 12 / 18 | 400 | Timestamps (always click-to-jump links) |
| `.text-wordmark` | Plus Jakarta Sans | 48 / 52, −0.04em | 700 | Reference only; use the logo files |

- **The serif rule matters most:** Newsreader means "these are the expert's exact words." Never use it for summaries, paraphrase, chatbot prose or headings.
- Sentence case everywhere ("New project", not "New Project"). No all-caps headings, except table headers, which may use `text-small` in uppercase with 0.04em tracking.
- **Marketing pages only:** for the hero headline you may scale `display` up to 48 / 52 (desktop) and 34 / 40 (mobile), weight 700, −0.03em. Body copy can go to 16 / 26.
- Manrope is included only as an alternate wordmark font. Don't use it in the UI.

## Spacing, radius, layout

- Spacing tokens: `--space-1` 4px, `--space-2` 8px, `--space-4` 16px, `--space-6` 24px. Larger gaps are multiples of 24 (48, 72, 96). Tailwind's default 4px scale lines up, so `p-4` = 16px.
- Radius: `--radius-sm` 4px (badges, highlights, checkboxes), `--radius-md` 8px (buttons, inputs), `--radius-lg` 12px (cards, panels, modals), `--radius-pill` 999px (status chips, waveform bars).
- **App layout:** 240px left sidebar (`surface-sunken`), content on `canvas`, a 400–480px transcript or chat side panel on the right (`surface-sunken`). The top bar is 56px tall on `surface` with a bottom `border`.
- **Marketing layout:** max content width 1120px, 24px side gutters (16px on mobile), sections 96px apart on desktop and 64px on mobile.
- Controls are 36px tall (32px compact). Hit areas are at least 32×32px.

## Components (recipes)

- **Primary button:** `accent` fill, `on-accent` text, `text-body` weight 600, height 36, padding 0 16px, `radius-md`. Hover: `accent-strong`. Disabled: `surface-sunken` fill, `ink-muted` text.
- **Secondary button:** `surface` fill, 1px `border-strong`, `ink` text. Hover: `surface-sunken` fill.
- **Ghost button:** no fill, `ink` text. Hover: `surface-sunken`.
- **Destructive button:** `surface` fill, 1px `recording` border, `recording` text.
- **Input / select:** `surface` fill, 1px `border-strong`, `radius-md`, height 36, padding 0 12px, `ink` text, `ink-muted` placeholder. Focus: 2px `ink` outline, offset 2px.
- **Card:** `surface`, 1px `border`, `radius-lg`, padding `space-4`. No shadow.
- **Table (transcript grid):** `surface` container with `radius-md` and a `border`. Header row is `surface-sunken` with `text-small` `ink-muted`. Rows are 44px tall, separated by `border`. Hover: `canvas`. Selected: `accent-soft`. Columns: expert name, former company, transcript title, date, duration, status.
- **Verified badge:** `accent-soft` fill, `accent-text` label "Verified", `text-small`, `radius-pill`, padding 2px 8px, with a check icon.
- **Quote card** (search results and chat answers): `surface` card. The quote is in `text-quote` with curly quotes. Below it, a `text-small` `ink-muted` line: "Expert title, former company · " plus a `text-timestamp` link in `accent-text` that jumps to that spot in the transcript. Add a Verified badge. Quote text must be shown exactly as stored; never trim words mid-quote without an ellipsis.
- **Transcript panel:** `surface-sunken`. Each turn shows the speaker name (`text-heading`), a timestamp link, then `text-body` lines. A found quote gets a `highlight` background with `radius-sm` and 2px horizontal padding, and scrolls into view when selected.
- **Chat panel:** user messages are right-aligned on `surface-sunken`. Assistant messages are left-aligned on `accent-soft` and set in `text-body`. Any quotes inside assistant answers render as quote cards, not inline prose.
- **Recording indicator:** an 8px `recording` dot that pulses (opacity 1 → 0.4, 1.2s), plus the label "Recording" and an elapsed timer in `text-timestamp`.
- **Sidebar nav:** items are 36px tall with `radius-md`. Inactive items use `ink-muted` text; hover uses `surface` fill. The active item has a `surface` fill, `ink` text, and a 3px `accent` bar on the left edge inside the item.
- **Project status chip:** `radius-pill`, `text-small`. "Open" uses `accent-soft` with `accent-text`. "Closed" uses `surface-sunken` with `ink-muted`.
- **Icons:** use Lucide (`lucide-react` or `lucide` static SVGs), 16px in UI and 20px in nav, 1.75 stroke, `currentColor`. No emoji anywhere.
- **Motion:** 120–160ms ease-out for hover and press, 200ms for panels sliding in. Respect `prefers-reduced-motion` (turn off the recording pulse and slides).

## Logo

The mark is a magnifying lens holding a waveform, with the center bar in teal: a search through a recording that lands on one exact moment.

| File | Use on |
| --- | --- |
| `logos/verelo-lockup-color.png` | **Default.** Light grounds: app header, sign-in, marketing nav. |
| `logos/verelo-lockup-color-reverse.png` | Dark grounds, `brand-panel`, dark mode header, footer. |
| `logos/verelo-lockup-navy.png` / `-white.png` | Single-ink situations only. |
| `logos/verelo-mark-color.png` | Favicon, app icon, spaces under 120px wide, light grounds. |
| `logos/verelo-mark-color-reverse.png` | Same, on dark grounds. |
| `logos/verelo-mark-navy.png` / `-white.png` | Single-ink mark. |
| `logos/verelo-wordmark-navy.png` / `-white.png` | Wordmark alone; only where the mark appears nearby. |

- The lockup in the header is 28px tall in the app and 32px tall on marketing pages. The mark alone is 24–32px.
- In dark mode, swap to the `-reverse` file (e.g. with `<picture>` and `prefers-color-scheme`, or by checking `data-theme`).
- The white bars in the color mark are **transparent cutouts**, so the color files only work on light grounds.
- Keep clear space equal to one waveform bar's width on all sides. Never recolor, stretch, outline, or add shadows.
- The wordmark is lowercase "verelo". In running text the product name is "Verelo".
- All logos are PNGs (about 2000px wide). For the favicon, export 32px and 180px PNGs from `verelo-mark-color.png`.

## Voice and copy

- Plain, short and direct. Sentence case. No exclamation marks or emoji.
- Buttons are verbs: "New project", "Start recording", "Search quotes", "Export PDF", "Close project".
- Always attribute quotes: "Former VP Network Ops, regional carrier · 00:24:17".
- Empty states say what to do next: "No transcripts yet. Record a call or import a recording to get started."

## Don'ts

- No gradients, glassmorphism, or blue-to-purple anything.
- No colored left-border accent cards, emoji, or decorative illustrations of people.
- No hard-coded hex values in components.
- No white text on teal.
- No serif outside verbatim quotes.
- No more than one teal-filled button per view.
