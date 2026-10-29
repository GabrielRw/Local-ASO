# Local ASO Tracker: Quiet Signal Design System

- **Status:** Ready for implementation
- **Version:** 1.0
- **Date:** 2026-10-29
- **Grid:** 4pt
- **Product:** Local ASO Tracker
- **Surface:** Local browser dashboard at `127.0.0.1`

---

## Implementation prompt

You are redesigning **Local ASO Tracker**, a local-first App Store keyword and
listing intelligence tool. Use the two supplied reference interfaces only for
principles: a persistent navigation rail, a center work surface, an optional
right context pane, quiet neutral colors, compact controls, restrained borders,
clear type hierarchy, and calm use of color. Do not copy GitHub or Copilot
branding, proprietary assets, exact layouts, or product-specific language.

Produce a complete implementation specification for a cohesive ASO workspace.
Every spacing, size, gap, padding, line-height, icon dimension, radius, and
layout dimension must resolve to a 4pt grid. Use semantic color only for
meaningful states. Keep the interface dense enough for daily operator use
without making text or controls illegibly small. The design must cover the
existing app shell, rank tracking, listing audit and health, paid search,
competitors, niche research, onboarding, tables, charts, modals, loading,
empty, and error states. Preserve the local-only product constraints, ranking
uncertainty, and original Local ASO identity.

Use this document as the build-ready source of truth.

---

## Reference analysis

### Reference A: three-pane operational workspace

What to carry forward:

- Persistent left navigation communicates location without competing with the task.
- A wide center pane prioritizes reading and primary actions.
- A right pane holds context, review, status, and secondary actions.
- Thin dividers and edge-aligned panels create structure with almost no shadow.
- Compact controls remain usable because spacing, alignment, and hierarchy are consistent.
- Active navigation uses a quiet neutral fill instead of a saturated brand block.
- Pale semantic surfaces distinguish resolved, warning, and review states without overwhelming content.

Avoid:

- Three equally prominent columns.
- Excessive pill shapes.
- Large unused vertical regions.
- Tiny metadata below practical readability.

### Reference B: editorial dashboard hierarchy

What to carry forward:

- A calm off-white canvas with white work surfaces.
- A clear global header and compact utility actions.
- One dominant task area per screen.
- A strong heading, short supporting copy, and immediate primary controls.
- Lists and tables separated by consistent borders rather than stacked shadows.
- A narrow right rail for utility content, status, or recommendations.
- Numeric data, badges, and secondary labels remain visually subordinate to names and actions.

Avoid:

- Product-specific branding.
- Large promotional blocks that displace operational content.
- Multiple accent colors in standard controls.
- Dense rows without enough whitespace for scanning.

---

## Product direction

### Name

**Quiet Signal**

### One-line definition

A calm, evidence-first operations desk for people who inspect App Store search
rankings, listing quality, paid targeting, and competitors every day.

### Desired impression

- Precise, local, and trustworthy.
- Dense without feeling cramped.
- Modern without looking fashionable for its own sake.
- Technical without looking unfinished.
- Soft and editorial without losing operational speed.

### Visual metaphor

Think of a well-organized analyst's desk: warm paper-like surfaces, sharp
labels, thin rules, compact instruments, and a few colored annotations that
mean something.

### Primary design principles

1. **Evidence before decoration.** Content and data create hierarchy; color is reserved for state.
2. **One task per focal region.** Each screen has one clear working surface.
3. **Quiet chrome.** Navigation, filters, and utilities recede until needed.
4. **Progressive disclosure.** Secondary context moves to a rail, drawer, or detail panel.
5. **Consistent density.** Similar tasks use similar row heights and control sizes.
6. **Uncertainty stays visible.** Missing ranks, unavailable Apple fields, and stale data are not visually collapsed into zeros.
7. **No ornamental color.** Neutral interaction controls; semantic color only for data and status.
8. **Every measurement snaps to 4pt.** Visual rhythm is consistent across screens.

---

## Color system

The dashboard remains light-first. Token names allow a future dark theme, but
dark mode is not part of this redesign scope.

### Core surfaces

| Token | Value | Use |
|---|---:|---|
| `--canvas` | `#F5F6F3` | App background |
| `--canvas-subtle` | `#EEF1ED` | Pressed/selected neutral regions |
| `--surface` | `#FFFFFF` | Cards, tables, sheets |
| `--surface-muted` | `#F8F9F7` | Sidebar, table headers, quiet sections |
| `--surface-hover` | `#F1F3F0` | Hovered neutral rows and controls |
| `--surface-selected` | `#EAF1EC` | Selected app, row, tab, or market |

### Borders and text

| Token | Value | Use |
|---|---:|---|
| `--border` | `#DFE3DF` | Default divider and outline |
| `--border-strong` | `#C9D0CA` | Input and emphasized control outline |
| `--ink` | `#202420` | Primary text and primary actions |
| `--ink-secondary` | `#5F6761` | Supporting copy |
| `--ink-tertiary` | `#858D87` | Metadata and placeholders |
| `--ink-disabled` | `#AEB4AF` | Disabled labels |

### Action and brand

| Token | Value | Use |
|---|---:|---|
| `--action` | `#202420` | Primary button, active tab, active navigation |
| `--action-hover` | `#111411` | Primary hover |
| `--action-contrast` | `#FFFFFF` | Text and icons on action |
| `--focus` | `#4E8065` | Focus ring |
| `--brand` | `#D65A38` | Logo and rare brand-only details |
| `--brand-soft` | `#FBECE7` | Brand annotation only |

### Semantic states

| Token | Value | Soft token | Use |
|---|---:|---:|---|
| `--positive` | `#247A55` | `#E4F2EA` | Improving, resolved, healthy, defended |
| `--warning` | `#A86C0A` | `#FFF4DB` | Opportunity, needs review, brand term |
| `--danger` | `#BD4658` | `#FBE8EC` | Declining, missing, repeated, failed |
| `--info` | `#3971A8` | `#E8F1F9` | Neutral information and competitor data |
| `--neutral` | `#7A827C` | `#EFF1EF` | Unknown, paused, inactive, pending |

### Color rules

- Standard buttons and tabs are black, white, or neutral.
- The coral brand token may appear in the logo and very small brand annotations only.
- Never use both a semantic color and a decorative color for the same state.
- Never encode meaning with color alone; pair it with text, an icon, or a label.
- Keep semantic fills below the visual weight of the main content.
- Avoid gradients except for image fallbacks or app artwork supplied externally.

---

## 4pt spacing system

All spacing uses the following tokens. Values outside this scale are not
allowed for padding, margin, gap, control sizing, or layout dimensions.

| Token | Value | Typical use |
|---|---:|---|
| `--space-0` | `0` | Flush alignment |
| `--space-1` | `4px` | Icon-to-label gap, tight inner detail |
| `--space-2` | `8px` | Input gaps, compact control spacing |
| `--space-3` | `12px` | Button horizontal padding, row padding |
| `--space-4` | `16px` | Default card padding, standard gap |
| `--space-5` | `20px` | Comfortable section padding |
| `--space-6` | `24px` | Section gap, card and content gutter |
| `--space-8` | `32px` | Page gutter, large group separation |
| `--space-10` | `40px` | Major content separation |
| `--space-12` | `48px` | Page-top breathing room |
| `--space-16` | `64px` | Hero-level separation |
| `--space-20` | `80px` | Empty-state room |
| `--space-24` | `96px` | Rare full-page separation |

### Grid rules

- Layout spacing, component height, component padding, icon boxes, radii, and gaps are multiples of 4.
- A 1px border/divider and a 2px focus or chart stroke are measured as strokes, not spacing.
- Line heights are multiples of 4: `12`, `16`, `20`, `24`, `28`, `32`, `40`, `48`.
- Do not optically compensate by introducing 2px, 6px, 10px, 14px, or 18px spacing.
- Use `calc()` only to account for 1px borders when preserving a 4pt outer dimension.

---

## Typography

### Font stack

```css
--font-sans: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-mono: "SFMono-Regular", ui-monospace, Menlo, Consolas, monospace;
```

Use the system stack when Inter is unavailable. Do not add a network font.

### Type scale

| Role | Size / line-height | Weight | Tracking | Use |
|---|---|---:|---:|---|
| Display | `32 / 40` | 620 | `-0.04em` | Empty-state or onboarding title |
| Page title | `24 / 32` | 620 | `-0.035em` | Main workspace heading |
| Section title | `18 / 24` | 620 | `-0.02em` | Major card heading |
| Card title | `15 / 20` | 600 | `-0.01em` | App, app section, competitor name |
| Body | `14 / 20` | 400 | `0` | Explanations and primary reading |
| Body compact | `13 / 20` | 400 | `0` | Dense operational copy |
| Control | `12 / 16` | 600 | `0.01em` | Buttons, tabs, fields |
| Label | `11 / 16` | 600 | `0.03em` | Kicker, field label, table header |
| Metadata | `10 / 12` | 500 | `0.01em` | Timestamps, supporting state |
| Numeric KPI | `28 / 32` | 650 | `-0.035em` | Main metric values |
| Numeric table | `12 / 16` | 650 | `0` | Ranks, estimates, budget |

### Typography rules

- Use tabular numbers for ranks, spend, counts, percentages, and chart labels.
- Do not use all caps for sentences. Reserve uppercase for short kickers and table headers.
- Avoid font sizes below 10px.
- Keep body copy at 14px where space allows; use 13px only inside data-dense panels.
- Limit paragraph width to `68ch`; use `52ch` in side rails.
- Use near-black rather than absolute black except for the dark action surface.

---

## Geometry

| Token | Value | Use |
|---|---:|---|
| `--radius-1` | `4px` | Tiny tags, inline annotation |
| `--radius-2` | `8px` | Inputs, buttons, app icons |
| `--radius-3` | `12px` | Cards, tables, grouped panels |
| `--radius-4` | `16px` | Modal, prominent empty state |
| `--radius-pill` | `999px` | Status and filter chips only |
| `--border-width` | `1px` | Dividers and outlines |
| `--control-height-sm` | `28px` | Dense inline utility |
| `--control-height` | `32px` | Filters, secondary actions |
| `--control-height-lg` | `36px` | Primary controls and fields |
| `--icon-sm` | `16px` | Inline icon |
| `--icon` | `20px` | Navigation and buttons |
| `--icon-lg` | `24px` | Page-level action |

### Elevation

Use borders first and shadows second.

```css
--shadow-raised: 0 1px 2px rgb(32 36 32 / 0.05);
--shadow-floating: 0 12px 32px rgb(32 36 32 / 0.12);
```

Only menus, tooltips, popovers, and dialogs use `--shadow-floating`.

---

## Application shell

### Desktop layout at 1440px and wider

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Brand / workspace switcher                              Search    Utilities │ 64
├───────────────┬───────────────────────────────────┬────────────────────────┤
│ Navigation    │ Primary workspace                 │ Context rail           │
│ 256           │ min 720                           │ 320                    │
│               │                                   │                        │
│ Rank tracking │ Page heading + primary actions    │ Selection summary      │
│ Niche         │ Filters and view switcher         │ Audit state            │
│ Apps          │ Main data card                    │ Recommendations        │
│               │ Supporting evidence               │ Recent activity        │
└───────────────┴───────────────────────────────────┴────────────────────────┘
```

### Shell dimensions

| Element | Value |
|---|---:|
| Global header | `64px` |
| Sidebar width | `256px` |
| Context rail width | `320px` |
| Page gutter | `32px` desktop, `24px` tablet, `16px` mobile |
| Content max width | `1440px` |
| Standard section gap | `24px` |
| Card padding | `24px` desktop, `20px` tablet, `16px` mobile |

### Layout rules

- Sidebar remains visible through `1200px`.
- At `1200–1439px`, reduce the context rail to `296px`.
- Below `1200px`, move context-rail content below the main content or into a drawer.
- Below `1024px`, collapse the sidebar into a global navigation drawer.
- Below `768px`, use a single column and replace side-by-side editors with stacked panels.
- The primary workspace never scrolls horizontally as a whole. Only tables, boards, matrices, and charts may scroll.

---

## Shared page anatomy

Each major screen uses this order:

1. **Page header** — title, one-line context, primary action.
2. **Summary strip** — app identity, market/device, freshness, or score.
3. **View controls** — segmented tabs, filters, search, secondary actions.
4. **Primary work surface** — table, matrix, board, or audit.
5. **Evidence area** — history, comparison, recommendations.
6. **Context rail** — only at wide widths; never required to complete the task.

### Page header

- Height: auto with minimum `48px`.
- Title and actions share one row on desktop.
- Actions wrap below the title below `768px`.
- Maximum supporting copy: two lines at `52ch`.
- Primary action: one black button only.

### Section rhythm

- Page top padding: `32px`.
- Gap after page header: `24px`.
- Gap between major cards: `16px`.
- Gap inside cards: `16px` or `24px`.
- Gap between data rows: `0`; use a `1px` divider.

---

## Sidebar

### Structure

- Brand row: `64px` high.
- Primary navigation: two text-led entries.
- App heading and add action.
- Scrollable app list.
- Footer: setup, local database status, version.

### Navigation item

| Property | Value |
|---|---:|
| Height | `36px` |
| Horizontal padding | `8px` |
| Icon | `20px` |
| Icon-label gap | `8px` |
| Radius | `8px` |

States:

- Default: transparent, secondary text.
- Hover: `--surface-hover`.
- Active: dark action surface and white content.
- Focus: 2px focus ring with 2px offset.

Do not use colored icon tiles. A 20px monochrome icon is enough.

### App row

| Property | Value |
|---|---:|
| Height | `52px` |
| Icon | `32px`, radius `8px` |
| Horizontal padding | `8px` |
| Gap | `8px` |
| Country badge | `24px` high |

- Selected row uses `--surface-selected`.
- Long names truncate after one line.
- Remove action appears in the row on hover/focus but remains visible on touch.

---

## Global header

- Height: `64px`.
- Left: brand and optional workspace name.
- Center: global search or command field, max width `480px`.
- Right: sync status, notifications if added, setup, settings.
- Icon buttons: `32px`.
- Search field: `36px` high.
- Header stays sticky.
- Separate header from content with a 1px border, not a shadow.

Search placeholder:

> Search apps, keywords, or actions

Keyboard hint:

> `/`

---

## Controls

### Buttons

| Variant | Height | Padding | Radius | Appearance |
|---|---:|---:|---:|---|
| Primary | `36px` | `0 16px` | `8px` | Dark surface, white label |
| Secondary | `32px` | `0 12px` | `8px` | White, 1px border |
| Ghost | `32px` | `0 8px` | `8px` | Transparent until hover |
| Danger | `36px` | `0 16px` | `8px` | Danger surface, white label |
| Icon | `32px` | `0` | `8px` | 20px icon |
| Inline text | `24px` | `0 4px` | `4px` | Underline on hover |

Button states:

- Hover: one surface step darker or lighter.
- Pressed: translate down `1px` only.
- Focus: 2px outline using `--focus`.
- Disabled: 45% opacity, no shadow.
- Loading: retain width; spinner at `16px`; disable interaction.

### Segmented tabs

- Outer height: `36px`.
- Inner tabs: `28px`.
- Outer padding: `4px`.
- Gap: `0`; use the surrounding control border as the visual separator.
- Radius: outer `12px`, inner `8px`.
- Active: dark fill, white text.
- Inactive: transparent, secondary text.
- Horizontally scroll on narrow screens; never compress labels below readability.

### Fields

- Height: `36px` for single-line controls.
- Text area padding: `8px 12px`.
- Label above: `11 / 16`.
- Help text below: `10 / 12`.
- Radius: `8px`.
- Border: `--border-strong`.
- Focus: border changes to `--focus`, plus 2px soft ring.
- Error: danger border and inline message below.

### Selects and comboboxes

- Match field height and radius.
- Show a 16px chevron with 8px right padding.
- Include the visible value, never an unlabeled empty control.
- Country controls show flag + ISO code; full country name remains in the menu and accessible label.

### Search

- Width: `240px` in dense toolbars, `320–480px` in the global header.
- Height: `32–36px`.
- Search icon: 16px.
- Clear action appears after text is entered.
- Debounce filtering by 120ms.

---

## Cards and surfaces

### Standard card

- Background: `--surface`.
- Border: 1px `--border`.
- Radius: `12px`.
- Padding: `24px` desktop, `20px` tablet, `16px` mobile.
- Shadow: none by default.
- Card title: `18 / 24`.

### Data card

- Header padding: `20px 24px 16px`.
- Table body runs edge-to-edge.
- Optional sticky header.
- Use one internal border grid; do not outline every cell.

### Metric card

- Height: `96px`.
- Padding: `16px`.
- Radius: `12px`.
- Label: `11 / 16`, sentence case.
- Value: `28 / 32`.
- Supporting note: `10 / 12`.
- Trend chip: `20px` high, `8px` horizontal padding.
- Clickable metric cards get a subtle border change and 1px lift only.

### Context card

- Minimum padding: `16px`.
- Use for selected keyword, audit state, or recommendations.
- Avoid nesting more than two bordered surfaces.

---

## Tables

### Desktop density

| Property | Value |
|---|---:|
| Header height | `36px` |
| Row height | `44px` |
| Vertical cell padding | `12px` |
| Horizontal cell padding | `12px` |
| Header type | `11 / 16`, 600 |
| Row type | `12 / 16` |
| Numeric cells | Right aligned, tabular |
| Row divider | 1px |

### Behavior

- First column stays sticky when horizontal overflow is necessary.
- Sortable headers show a 16px arrow.
- Hovered rows use `--surface-hover`.
- Selected rows use `--surface-selected`.
- Bulk actions appear only when at least one row is selected.
- Use row-level progress for asynchronous checks; never use a full-screen loader.
- Missing ranks display `>limit`, not `0`.

### Mobile table transformation

- Convert rows to stacked data records.
- Minimum row height: `72px`.
- Keyword and rank occupy the first row.
- Volume and difficulty occupy the second row.
- Hide low-priority metadata behind an overflow action.
- Preserve the uncertain result label.

---

## Status and data display

### Status chip

- Height: `24px`.
- Horizontal padding: `8px`.
- Radius: `8px`, not a pill unless it is a filter.
- Dot: `8px`.
- Label: `10 / 12`, 600.

Examples:

- `● Defend` — positive
- `● Close wins` — warning
- `● Weak visibility` — danger
- `● Checking` — neutral with animated dot
- `▲ +12.1% · 7d` — positive trend
- `▼ −4.8% · 7d` — danger trend

### Rank uncertainty

- Exact found rank: `#12`
- Missing within result window: `>200`
- Not checked: `—`
- Failed: `! Check failed`

Never substitute zero for a missing rank.

### Estimates

- Label the model on first use: `Estimated from public ratings`.
- Use a 4px progress track and a numeric value.
- Volume tones: positive, warning, danger, neutral.
- Difficulty tones: inverse meaning but consistent color semantics.
- Unknown estimate: `—` with accessible explanation, not an empty bar.

---

## Listing audit and health

This is the most editorial screen in the product.

### Audit editor

- Step indicator: three compact items, `32px` high.
- Editor fields: `40px` high.
- Field labels align with character counters.
- Highlights render inside native editable fields.
- Branded terms: warning-soft.
- Repeated terms: danger-soft with strikethrough.
- Unique terms: positive-soft.
- Legend sits inside the audit form, below the inputs.
- Autosave status appears at the top-right in metadata type.

### Health score

- Hidden until audit metadata is saved.
- Calculated only from the saved listing strategy audit.
- Keyword repetition contributes up to `70` points; each extra repeated use costs `15` points.
- Goal-specific title order contributes up to `30` points.
- Public listing fields do not contribute to the score.
- Score ring: `112px` desktop, `88px` tablet.
- Ring thickness: `8px`.
- Score number: `32 / 40`.
- Label: `24 / 32`.
- Supporting copy: `13 / 20`.

### Score breakdown

- One row per signal.
- Use two rows only: `Keyword repetition` and `Title order`.
- Row minimum height: `56px`.
- Grid: icon `32px`, label flexible, progress `160–240px`, value `48px`.
- Repeated-word reductions use warning/danger semantics, not hidden deductions.

### Audit workflow

1. Goal and market.
2. Listing metadata.
3. Strategy audit and score.

Do not split the editor and visual annotations into separate cards.

---

## Charts

### Shared chart rules

- Container minimum height: `240px`.
- Chart plot area padding: `24px 16px 32px 40px`.
- Gridline: 1px neutral.
- Axis labels: `10 / 12`, tertiary.
- Series line: 2px.
- Data point: 8px diameter with 2px surface ring.
- Hover/focus tooltip: dark floating surface, max width `280px`.
- Zero and missing values must be visually distinct.

### Rank charts

- Lower numeric rank is better.
- Invert the y-axis so an improving rank rises.
- Label intermediate ranks as `#1`, `#73`, `#146`.
- Show start and end dates below the plot.

### Trend charts

- Use positive for improvements, danger for declines.
- Do not use area gradients.
- Use a single 2px line and quiet grid.

---

## Competitor views

### Matrix

- Sticky keyword column width: `216–240px`.
- App column width: `144–176px`.
- Header app icon: `32px`.
- Rank cell: `12 / 16`, tabular.
- Use positive/neutral/danger rank groupings only when justified.
- Horizontal scrolling is expected and persistent.

### Losing-to cards

- Minimum height: `52px`.
- Padding: `8px 12px`.
- Layout: app icon `36px`, name and rating line, ahead count.
- Name: `15 / 20`.
- Rating line: `10 / 12`, `★ 4.8 · 44.1k ratings`.
- Ahead count: `16 / 20`, danger or warning.
- Border: 1px.
- Radius: `12px`.
- Two columns below `1200px`; one column below `640px`.

---

## Paid search

- Keep account selection and sync in the page header.
- Summary metrics use the standard metric card.
- Countries are filters, not campaigns.
- Paused rows are hidden by default.
- Table headers sort all comparable numeric values.
- Status text and semantic color always appear together.
- Spend uses tabular numbers and the account currency.
- Empty or denied API states appear inline; do not block the rest of the dashboard.

---

## Niche research

### Desktop

- Board: flexible main column.
- Agent: sticky right column, `320px`.
- Board header: name, brief, market columns, last checked.
- Country columns: minimum `132px`.
- Cell dimensions: `96px × 28px` or compact equivalent.
- One cell combines volume and difficulty without more than two colors.

### Agent composer

- Bottom-anchored inside the right rail.
- Text area: minimum `80px`.
- Provider selector and submit action share a `36px` row.
- Submission button remains visually primary.

### Country management

- Add-country control lives in the board toolbar.
- Each column header exposes remove on hover/focus.
- Horizontal scrolling is allowed; vertical page scrolling must remain stable.

---

## Onboarding

- Modal width: `640px` maximum.
- Padding: `32px`.
- Progress step: `24px` marker plus `8px` gap.
- One primary action per step.
- Back is secondary.
- Close is icon-only and top-right.
- Keep setup copy practical and under three short paragraphs per step.
- Collect app, market, device, optional initial keywords, and optional local agent.
- Never require cloud credentials.

---

## Dialogs, sheets, and feedback

### Modal

- Width: `480–640px` depending on task.
- Padding: `24px`.
- Radius: `16px`.
- Border: 1px.
- Overlay: `rgb(20 24 21 / 0.42)` plus 2px blur.
- Footer actions: secondary left, primary right.

### Drawer

- Width: `320–400px`.
- Full height beneath the header.
- Used for filters, context, and mobile navigation.

### Toast

- Bottom-right desktop; bottom-center mobile.
- Max width: `360px`.
- Padding: `12px 16px`.
- Radius: `12px`.
- Auto-dismiss after 3.5 seconds unless persistent error.

### Tooltips

- Max width: `280px`.
- Padding: `8px 12px`.
- Radius: `8px`.
- Dark surface, white text, `10 / 16`.

---

## Loading, empty, and error states

### Loading

- Skeleton blocks: `8px` radius.
- Animate opacity or background position only.
- Use row-level skeletons or status labels for data refreshes.
- Full-screen loading is reserved for first boot or app initialization.

### Empty

- Icon container: `48px`.
- Vertical padding: `48–64px`.
- Title: `18 / 24`.
- Copy: `13 / 20`, maximum `52ch`.
- One primary next action.

### Error

- Inline message above or within the affected region.
- Include what failed, what remains available, and the next action.
- Never expose raw Apple payloads or credentials.

---

## Iconography

- Use 20px line icons with a 1.5–1.75px stroke.
- Use 16px icons inline with compact labels.
- Filled icons only for selected states or brand artwork.
- Do not place colored icon tiles in navigation.
- Icons never replace labels in primary navigation.
- Decorative icons use `aria-hidden="true"`.

---

## Motion

| Token | Duration | Use |
|---|---:|---|
| `--motion-fast` | `80ms` | Button press |
| `--motion-control` | `120ms` | Hover, focus, selected change |
| `--motion-panel` | `180ms` | Drawer or modal entry |
| `--motion-chart` | `240ms` | Chart line reveal |

Use ease-out for entries and ease-in for exits. Do not animate layout width or
height during typing or data refresh. Respect `prefers-reduced-motion`.

---

## Responsive behavior

### `>= 1440px`

- Sidebar `256px`.
- Main workspace flexible.
- Context rail `320px`.

### `1200–1439px`

- Sidebar `248px`.
- Context rail `296px` or collapses on content-heavy screens.
- Metric cards may reduce to two columns.

### `1024–1199px`

- Sidebar becomes a `72px` icon rail or opens as a drawer.
- Context rail moves below primary content.
- Tables preserve horizontal scroll.

### `768–1023px`

- Global header remains `56px`.
- Sidebar opens as a drawer.
- Page gutter is `24px`.
- Segmented tabs may horizontally scroll.
- Cards generally remain two columns.

### `< 768px`

- One-column layout.
- Page gutter `16px`.
- Section gap `16px`.
- Primary page actions can become full width.
- Modals become bottom sheets above `640px` viewport; otherwise near-fullscreen dialogs.
- Tables transform to stacked records.
- Touch targets are at least `44px`, even when the visible control is `36px`.

---

## Accessibility

- Meet WCAG AA contrast for all text and interactive controls.
- Never use color alone to convey rank, health, volume, or difficulty.
- Every icon-only control has an accessible label and tooltip.
- Focus-visible ring: 2px `--focus`, 2px offset.
- Maintain a logical tab order.
- Keyboard access is required for tabs, menus, dialogs, filters, and chart points.
- Sticky headers cannot obscure focused elements.
- Table sort state uses `aria-sort`.
- Live sync messages use `role="status"`.
- Error messages use `role="alert"` only when immediate attention is needed.
- Support `prefers-reduced-motion`.
- Minimum pointer target is `32px` desktop and `44px` touch.

---

## Content rules

- Prefer concrete labels over metaphors.
- Use sentence case.
- Keep button labels verb-led: `Add keyword`, `Run check`, `Save audit`.
- Avoid exclamation marks in operational UI.
- State data freshness explicitly: `Updated 9 days ago`.
- State unavailable data precisely: `Not exposed by Apple`.
- Preserve Apple terminology where it prevents ambiguity.
- Never claim downloads, search volume, popularity, or difficulty when data is estimated.
- Keep tooltips short enough to scan in one or two lines.

---

## CSS token starter

```css
:root {
  --canvas: #f5f6f3;
  --canvas-subtle: #eef1ed;
  --surface: #ffffff;
  --surface-muted: #f8f9f7;
  --surface-hover: #f1f3f0;
  --surface-selected: #eaf1ec;

  --border: #dfe3df;
  --border-strong: #c9d0ca;
  --ink: #202420;
  --ink-secondary: #5f6761;
  --ink-tertiary: #858d87;
  --ink-disabled: #aeb4af;

  --action: #202420;
  --action-hover: #111411;
  --action-contrast: #ffffff;
  --focus: #4e8065;
  --brand: #d65a38;

  --positive: #247a55;
  --positive-soft: #e4f2ea;
  --warning: #a86c0a;
  --warning-soft: #fff4db;
  --danger: #bd4658;
  --danger-soft: #fbe8ec;
  --info: #3971a8;
  --info-soft: #e8f1f9;
  --neutral: #7a827c;
  --neutral-soft: #eff1ef;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;
  --space-24: 96px;

  --radius-1: 4px;
  --radius-2: 8px;
  --radius-3: 12px;
  --radius-4: 16px;

  --control-height-sm: 28px;
  --control-height: 32px;
  --control-height-lg: 36px;
  --icon-sm: 16px;
  --icon: 20px;
  --icon-lg: 24px;

  --shadow-raised: 0 1px 2px rgb(32 36 32 / 0.05);
  --shadow-floating: 0 12px 32px rgb(32 36 32 / 0.12);

  --motion-fast: 80ms;
  --motion-control: 120ms;
  --motion-panel: 180ms;
  --motion-chart: 240ms;
}
```

---

## Existing component mapping

| Existing component | Target treatment |
|---|---|
| `.app-shell` | CSS Grid shell with `256px` sidebar and flexible workspace |
| `.sidebar` | Border-led navigation rail with `36px` items |
| `.nav-item.active` | Dark neutral selected state |
| `.nav-icon` | Monochrome `20px` icon, no colored tile |
| `.app-list-row` | `52px` selected app row |
| `.tabs` / `.tab` | Compact segmented control |
| `.tabs-bar` | 1px-bordered control bar, no elevated card |
| `.select-wrap` | `32–36px` neutral field |
| `.button-primary` | Near-black primary action |
| `.button-ghost` | White bordered secondary action |
| `.metric` | `96px` border-led metric card |
| `.data-card` | Single main table surface |
| `.rank-table` | `44px` desktop rows, sticky header and first column |
| `.country-rank-card` | Compact market filter/summary card |
| `.country-visibility` | Horizontal scroll with equal-height cards |
| `.coverage-card` | Three-step audit surface |
| `.coverage-token-shell` | Native editor with inline semantic highlights |
| `.health-score-card` | Hidden until audit completion; distinct score ring afterward |
| `.breakdown-card` | Border-separated score rows |
| `.losing-card` | Compact two-row competitor cards with rating evidence |
| `.niche-layout` | Flexible board plus `320px` agent rail |
| `.modal` | 16px radius, overlay, 24px padding |
| `.toast` | Bottom-right low-chrome status |

---

## Suggested implementation sequence

1. Add all design tokens to the root stylesheet and remove ad hoc values from touched components.
2. Rebuild the shared shell, sidebar, global header, page headers, and segmented controls.
3. Normalize buttons, fields, tabs, chips, tooltips, dialogs, and feedback states.
4. Redesign the keyword screen around the metrics, table, charts, and losing-to cards.
5. Redesign the listing audit and health score using the same editor and card rules.
6. Align paid search, competitor matrix, and niche research with the shared table/card grammar.
7. Apply responsive transformations.
8. Run visual QA at `1440`, `1280`, `1024`, `768`, and `390` widths.
9. Re-run format, lint, type checks, JavaScript syntax checks, and the full test suite.

---

## Visual QA checklist

- Every spacing and dimension is a multiple of 4, except 1px strokes.
- The page has one primary action, not multiple competing primary buttons.
- Standard controls contain no saturated colors except focus and state.
- Card heights are consistent within each group.
- Tables align numeric values and use tabular figures.
- Long names truncate with an accessible full value.
- No text falls below 10px.
- Focus is visible on every interactive element.
- Loading never blocks the entire page for a row-level refresh.
- Missing ranks remain `>limit` or `—`, never `0`.
- Health score stays hidden until the Keyword coverage audit is saved.
- Repeated audit keywords visibly lower the health score.
- "Losing to" cards show average rating and rating count.
- Mobile layouts retain the same hierarchy without horizontal page scrolling.
- All content remains original to Local ASO Tracker.
