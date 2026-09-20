# Offline image review studio design system

## 0. Design intent

A dense desktop instrument, not a marketing surface: layered dark chrome,
keyboard-first controls and restrained accents. The image is the focal object,
with a quiet canvas, compact inspection rail and accessible action belt.
Reports are generic by default and accept a title/subtitle at build time.
Committed demo screenshots use synthetic placeholders only.

## 1. Atmosphere & Identity

The gallery is a quiet command center for inspecting a noisy visual corpus. It should feel like a precision instrument: blue-black void, cool contained surfaces, compact mono metrics, and one red warning accent for routing risk. The signature is the thin blue focus line and double-ring surface treatment that makes every control feel inspectable without becoming ornamental.

## 2. Color

### Palette

| Role | Token | Value | Usage |
|------|-------|-------|-------|
| Canvas | `--color-canvas` | `#07080a` | Page background |
| Canvas deep | `--color-canvas-deep` | `#050608` | Footer and table gutter |
| Surface | `--color-surface` | `#101111` | Cards and table header |
| Surface elevated | `--color-surface-elevated` | `#17191b` | Family panel and lightbox |
| Surface active | `--color-surface-active` | `#202326` | Selected filters and row hover |
| Text primary | `--color-text-primary` | `#f4f5f5` | Headings and values |
| Text secondary | `--color-text-secondary` | `#c4c7c9` | Labels and filenames |
| Text muted | `--color-text-muted` | `#878c91` | Metadata and helper text |
| Border | `--color-border` | `#25292c` | Containment and dividers |
| Border subtle | `--color-border-subtle` | `rgba(255,255,255,.07)` | Quiet separators |
| Accent info | `--color-info` | `#55b3ff` | Links, focus, selected states |
| Accent danger | `--color-danger` | `#ff6363` | NSFW and route warnings |
| Accent warning | `--color-warning` | `#ffbc33` | Uncertain and gaming states |
| Accent success | `--color-success` | `#5fc992` | Archive candidates and positive signals |
| Accent info soft | `--color-info-soft` | `rgba(85,179,255,.14)` | Selected filters and quiet info surfaces |
| Accent danger soft | `--color-danger-soft` | `rgba(255,99,99,.14)` | Risk badges and NSFW surfaces |
| Accent warning soft | `--color-warning-soft` | `rgba(255,188,51,.14)` | Review and caution surfaces |
| Accent success soft | `--color-success-soft` | `rgba(95,201,146,.14)` | Archive and stable-signal surfaces |
| Character accent | `--color-character` | `#b8a1ff` | Face boxes, cluster identity affordances |
| Character accent soft | `--color-character-soft` | `rgba(184,161,255,.16)` | Face popovers and selected character states |
| Focus ring | `--color-focus` | `#8bd0ff` | Keyboard focus and active image frame |
| Scrim | `--color-scrim` | `rgba(5,6,8,.76)` | Fullscreen overlays and NSFW privacy |
| Canvas glow | `--color-canvas-glow` | `rgba(85,179,255,.07)` | Non-interactive ambient depth |

### Rules

- Use the blue accent for interaction and the red accent only for risk; do not turn every badge into a highlight.
- Surface hierarchy uses cool tonal shifts plus double-ring shadows. No decorative gradients or external imagery.
- All generated HTML colors route through CSS custom properties declared in this table.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| Display | `clamp(28px, 4vw, 42px)` | 600 | 1.05 | Report title |
| Section | 20px | 600 | 1.2 | Spotlight headings |
| Body | 14px | 500 | 1.45 | Controls and prose |
| Caption | 12px | 600 | 1.3 | Labels, badges, metadata |
| Metric | 13px | 600 | 1.2 | Scores and counts |
| Code | 12px | 600 | 1.35 | SHA, paths, family IDs |

### Font Stack

- Primary: `system-ui, "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif` — CJK-safe and system-only for file:// portability.
- Mono: `ui-monospace, "Cascadia Mono", "SFMono-Regular", Consolas, monospace` — paths, IDs, scores, and table headers.

## 4. Spacing & Layout

### Base Unit

All spacing derives from 4px: `--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 20px, `--space-6` 24px, `--space-8` 32px, `--space-10` 40px.

- Max content width: none; the app shell occupies `100dvh` and uses the full viewport at every width.
- Breakpoints: 520px compact, 760px narrow, 900px drawer overlay, 1200px spotlight rail, 1440px inline drawer.
- Primary layout: the app shell owns the viewport; the top header and controls row stay pinned, while the table region owns vertical and horizontal scrolling. The spotlight rail and drawer body have their own named scroll owners.
- At `min-width: 1440px`, row and family details reserve a 420px right drawer beside the table. Below 900px, the drawer becomes a full-height overlay.
- Mobile fallback: summary cards, disposition cards, and flag chips wrap naturally; the table remains a labelled horizontal viewport whose overflow never escapes the table region.
- Review studio: the shell is a bounded `100dvh` grid. Header and mode controls stay fixed; the studio body owns vertical overflow; the preview canvas owns image pan/zoom; the inspector and filmstrip own their named local scroll regions. At compact widths the inspector moves below the preview and the action belt remains reachable without page-level horizontal overflow.
- Primary review geometry: preview `minmax(0, 1fr)`, inspector `minmax(288px, 360px)`, filmstrip `96px` high, action belt `auto`. The table is a secondary mode and retains its contained two-dimensional scroll region.

## 5. Components

### Disposition card

- **Structure**: button with tier label, count, and accent rule.
- **Variants**: queue, review, archive candidate, route NSFW, route identity, selected.
- **Spacing**: `--space-3` to `--space-4`.
- **States**: default, hover, active, focus, selected.
- **Accessibility**: native button, `aria-pressed`, visible focus ring.
- **Motion**: 120ms opacity/transform feedback only.

### Filter chip and active-filter cluster
- **Structure**: wrapped native buttons for flag filters plus removable active-filter buttons and a clear action.
- **Variants**: unselected, selected, removable, disabled clear state.
- **Spacing**: `--space-1` to `--space-3`.
- **States**: default, hover, selected, focus, empty-filter summary.
- **Accessibility**: `aria-pressed`, visible focus ring, explicit Chinese labels, keyboard reachable.
- **Motion**: 120ms color/transform feedback only.

### Audit table

- **Structure**: labelled table inside an overflow viewport; each row carries a stable `data-key`.
- **Variants**: default, filtered, empty, NSFW-private, missing-thumbnail.
- **Spacing**: `--space-2` row rhythm, `--space-3` header and cell padding.
- **States**: sortable headers with visible `▲`/`▼`, active sort column, row hover, selected family, thumbnail reveal, empty cells.
- **Accessibility**: native table semantics, text alternatives for metrics, keyboard buttons for images and links.
- **Motion**: no automatic row animation; focus and reveal use 120ms opacity/filter transitions.

### Review studio

- **Structure**: `studio-shell` with a preview stage, inspector, action belt, neighbor filmstrip, and a secondary virtualized table mode.
- **States**: loading, loaded, missing asset, NSFW blurred, NSFW revealed, fit, 100% zoom/pan, selected, manually decided, filtered empty.
- **Action belt**: native buttons for `精选`, `入队通过`, `归档`, `NSFW 确认`, `身份存疑`, `跳过`; shortcuts `1–6`, `J/K`, arrows, `U`, Space, `F`, `?` are always visible in the help dialog.
- **Persistence**: manual decisions and an append-only action journal use a localStorage key derived from the embedded corpus fingerprint. The pipeline's `proposed_tier` is never overwritten.
- **Accessibility**: preview has a live item label, inspector exposes the supported score fields including Q-ReAlign and raw `hpsv3_mu` / `hpsv3_sigma` as `HPSv3 μ` / `HPSv3 σ`; missing HPS values remain visible as `—`, never zero. Detail tooltips preserve source numeric precision and the field count is derived from displayed fields. Unknown CSV columns remain tolerated but are not automatically rendered. Action buttons expose pressed/current state, the filmstrip is a labelled list of buttons, and overlays trap focus by returning focus to their trigger.
- **Motion**: 120ms feedback for controls; 200ms opacity/transform for mode and panel changes; no layout-property animation; reduced motion removes non-essential transforms.

### Face overlay

- **Structure**: a positioned overlay layer shares the preview image's contain box and transform; each face is a native button with an optional confirmed-name chip.
- **Variants**: unlabelled, confirmed, ignored, wrong-box, uncertain, outlier, NSFW-private.
- **Spacing**: face chips use `--space-1` and `--space-2`; the layer itself is bounded by the preview canvas.
- **States**: default, hover, focus, selected, popover-open, hidden when identity metadata is absent.
- **Accessibility**: every face is a labelled button exposing face ID, cluster, confidence and current name; `N` opens the first unlabeled face, `Tab` cycles faces and `Esc` closes the popover.
- **Motion**: 120ms border/opacity feedback; the anchored name popover uses opacity plus transform only and becomes instantaneous under reduced motion.

### Character panel

- **Structure**: a fixed right drawer with a virtualized cluster list, lazy representative crops and decision actions.
- **Variants**: absent, loading, populated, active-learning queue, empty-filter, merged/split/outlier decision states.
- **Spacing**: `--space-3` to `--space-5` shell rhythm and `--space-2` cluster-card gaps.
- **States**: closed, open, keyboard-focused, crop-missing, selected cluster, pending decision.
- **Accessibility**: labelled dialog, Escape/backdrop close, native buttons and progress text; no action depends on hover.
- **Motion**: reuse the existing drawer's 200ms transform/opacity mechanism; reduced motion uses opacity only.

### Character grouping view

- **Structure**: a third top-level tab beside `审查工作台` and `审计表格`, with a compact threshold banner, an intrinsic card grid, and a filtered ledger summary.
- **Character card**: native button with character name, unique image count, face count, mean similarity, minimum margin, and the active threshold provenance. A separate `未定` card represents empty roles and abstained faces, including fallback cluster labels.
- **States**: absent (the tab is hidden), loading, populated, selected, empty-filter, and experimental-warning.
- **Accessibility**: cards expose `aria-pressed`, counts are text (not color-only), the unassigned backlog has a labelled `仅看未定` toggle, and the source/licensing note remains visible in the view.
- **Interaction**: selecting a card sets the shared ledger filter and `state.visible` navigation queue; `未定` also exposes a one-click naming entry into the existing face popover and journal flow. Image roles come from `character-groups-by-image.csv`, while face labels come from `character-groups-by-character.csv`.
- **Face badges**: the preview may show multiple role badges for a multi-character image. Assigned face labels use the grouping character; abstained faces fall back to cluster ID and expose similarity, margin, and decision in the existing tooltip.
- **Motion**: card selection uses the existing 120ms control feedback; mode changes reuse the 200ms opacity/transform contract and become instantaneous under reduced motion.

### Character grouping provenance note

- Grouping is an experimental, uncalibrated retrieval proposal; it is not identity verification or an accuracy claim.
- Thresholds show `min_sim` and `min_margin` from the grouping artifact. Folder names are human-supplied labels; per-image decisions use pixels only. Source-image rights remain user-supplied and unverified.

### Character decision journal

- **Structure**: append-only localStorage events keyed by the corpus fingerprint, with import/export controls in the existing journal modal.
- **Variants**: confirm, new, ignore, wrong-box, merge, split, outlier, undo.
- **Spacing**: existing journal toolbar and export-row tokens.
- **States**: no labels, partially named, complete, imported, undoable.
- **Accessibility**: exact Chinese action labels, visible status text, file input labelled for importing a labels JSON.
- **Motion**: no automatic entry animation; export/import feedback uses the existing micro transition only.

### Virtualized table

- **Structure**: semantic sticky-header table with a single delegated body listener and a spacer row; only the visible row window plus overscan is mounted.
- **Budget**: row window is bounded to roughly 48 rows on a 24px row rhythm; sort keys are precomputed once per sort; filter/sort work is scheduled before a single `requestAnimationFrame` paint.
- **Media**: table images use `loading="lazy"` and `decoding="async"`; idle warmup only touches a small viewport-adjacent window.

### Family panel
- **Structure**: fixed right-side detail drawer with a member strip, raw-field inspector, copy actions, and close button.
- **Variants**: populated family, singleton family, family with missing member, empty family.
- **Spacing**: `--space-4` shell, `--space-2` member gaps.
- **States**: open, closed, focus-visible; singleton metadata is explicit and keeps the member strip to one card.
- **Accessibility**: labelled region, Escape closes, member buttons jump to their table row.
- **Motion**: 200ms transform/opacity slide; reduced motion disables the transform.

### Uncertainty queue

- **Structure**: a toggleable ordered face review lane in the character drawer, with a bounded progress indicator.
- **Variants**: standard cluster order, uncertainty-first order, complete, no faces.
- **Spacing**: `--space-2` list rhythm and `--space-3` queue header.
- **States**: off, on, focused face, named, pending.
- **Accessibility**: native toggle with `aria-pressed`; ordering rationale is visible as Chinese helper text.
- **Motion**: reorder is immediate; only focus and selected-state opacity changes animate, and reduced motion removes transitions.

### Metric legend modal
- **HPS evidence**: `HPSv3 μ` is the raw preference mean; `HPSv3 σ` is native standard deviation, not a sixth scorer or a calibrated confidence interval. Both appear even on legacy reports to explain unavailable evidence. Reuse existing metric cards, glossary items and CJK-safe labels; no new visual tokens.
- **Structure**: labelled modal with a two-column metric glossary and direction/caveat notes.
- **Variants**: closed, open, narrow one-column glossary.
- **Spacing**: `--space-4` to `--space-6`.
- **States**: open, closed, Escape/backdrop close, focus restore.
- **Accessibility**: labelled dialog, native close button, keyboard focus, no semantic claim beyond the pipeline's documented caveats.
- **Motion**: opacity-only open/close; reduced motion removes transitions.

### Lightbox

- **Structure**: fixed backdrop, elevated preview panel, preview image, original-file link.
- **Variants**: preview available, missing preview placeholder.
- **Spacing**: `--space-4` to `--space-6`.
- **States**: closed, open, Escape/backdrop close, original link.
- **Accessibility**: dialog-like labelling, focus-visible controls, image alt text from filename.
- **Motion**: 200ms opacity/scale; reduced motion disables the scale.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 120ms | `ease-out` | Hover, press, focus ring |
| Standard | 200ms | `cubic-bezier(.16,1,.3,1)` | Panel and lightbox open |

- The interaction reference is beui.dev's restrained `table` + `drawer` mechanism, adapted to vanilla CSS/JS; no runtime dependency is added.
- Animate only `transform`, `opacity`, and `filter`.
- `prefers-reduced-motion: reduce` disables non-essential transitions and transforms.
- `/` focuses search; Escape and backdrop clicks close the active drawer or modal; focus returns to the triggering control.
- NSFW previews blur by default at `nsfw_prob >= 0.65` or `route_nsfw`, with a visible `点击显示` action.
- Face overlays inherit the same privacy state as the image. Hidden/blurred media never gets an extra unblurred crop request in the preview stage; crops in the character drawer use the same private class when their source image is private.
- Identity metadata is optional. If `identities.json` is absent or incomplete, the face layer stays hidden without an empty panel or console error. Unknown producer fields are retained in the embedded metadata for forward compatibility.
- Overlay coordinates are normalized from source pixels into the rendered contain rectangle, then transformed with the image's zoom/pan matrix. The image and overlay share one positioned media frame so the boxes cannot drift during zoom or pan.
- Review media uses preview-first resolution (`previews/<sha16>.jpg` → `thumbs/<sha16>.jpg` → placeholder) and swaps sources in place without clearing the current bitmap. Next/previous six items are prefetched with a bounded queue and stale requests are cancelled.

## 7. Depth & Surface

The strategy is **mixed**: thin cool borders for table structure plus Raycast-inspired double-ring shadows for elevated panels. Elevated surfaces use `0 0 0 1px` outer containment, an inset top highlight, and a dark inset edge; no pure black drop shadows are used.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- WCAG 2.2 AA target; body contrast floor 4.5:1; every interactive element has a visible focus state.
- Full keyboard access for filters, sort headers, family panel, lightbox, and original links.
- Native `button`, `a`, `input`, `table`, and `dialog-like` landmarks are preferred over click handlers on generic elements.
- Privacy blur is never the only indication: NSFW rows also expose a text badge and an explicit reveal action.
- Chinese labels use the system CJK-safe stack; numeric and path values use the mono stack and may wrap in the drawer.
- The report remains file://-first: unsupported `DecompressionStream` surfaces a blocking Chinese compatibility message with the output directory and a plain-text fallback hint rather than a silent blank page.

### Accepted Debt

| Item | Location | Why accepted | Owner / Exit |
|------|----------|--------------|--------------|
| Horizontal audit table on narrow screens | generated `gallery.html` | All score columns remain available to a power user; collapsing them would hide evidence. The scrollbar is contained inside the table region and never expands the page. | Revisit if a mobile-specific audit view is requested. |

## 9. Performance contract

- Payload is a short-key columnar JSON object compressed with gzip and base64-encoded by Python. The browser uses native `DecompressionStream("gzip")`; there is no framework, CDN, fetch, XHR, or network fallback.
- Report build logs raw JSON bytes, compressed bytes, base64 bytes, and estimated HTML payload delta. The target is at least 50% smaller than the prior row-object JSON for the same CSV.
- Image prefetch uses six neighbors by default, a four-request concurrency cap, `Image.decode()` when available, and an `AbortController` generation token to ignore stale work.
- CSS uses `contain`, `content-visibility`, bounded overflow, and transform/opacity-only motion. Manual QA records table scroll smoothness because a static artifact cannot promise a device-specific frame rate.
