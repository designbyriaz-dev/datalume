# DataLume — Design System (from approved mockups)

Two approved reference mockups define the visual language:

1. **App dashboard** (light theme) — the authenticated product experience.
2. **Marketing landing page + sign-in** (dark theme) — the logged-out
   experience.

The original PNG mockups were not preserved as files in this handoff — the
descriptions below are a faithful written spec of both screens, precise
enough to implement pixel-close. Treat this document as authoritative for
styling; re-generate reference screenshots from it early in the build and
confirm against stakeholder expectations before scaling the pattern across
every screen.

---

## 1. Brand

- Logo: a simple rounded house/roof glyph (line icon, not filled), paired
  with wordmark **"DataLume"** (bold) + small-caps subtitle **"PROPERTY
  INTELLIGENCE"** beneath it.
- Tagline (footer / auth screens): **"ONE PROPERTY. ONE VIEW. EVERY
  SIGNAL."**
- Marketing headline style: short, confident, two-line hero statements
  ("Turn your property data into brighter decisions.").

## 2. Color tokens

Two modes exist simultaneously in the product — not a light/dark toggle of
the same screen, but a light app shell and a dark marketing/auth shell.
Define both as design tokens.

### Shared brand colors
| Token | Hex (approx) | Use |
|---|---|---|
| `--color-primary` | `#2563EB` (cobalt/electric blue) | primary buttons, active nav, links, chart accent |
| `--color-primary-hover` | `#1D4ED8` | button hover |
| `--color-accent-cyan` | `#06B6D4` | sparingly, secondary highlights (e.g. "Ask DataLume" sparkle) |
| `--color-success` | `#10B981` (green/teal) | compliant, positive trend, processed status |
| `--color-warning` | `#F59E0B` (amber) | due soon, medium priority |
| `--color-critical` | `#EF4444` (red) | overdue, high priority, critical alerts |
| `--color-purple-accent` | `#7C3AED` | avatar/identity accents |

### Light app theme (dashboard)
| Token | Hex (approx) | Use |
|---|---|---|
| `--bg-app` | `#F8FAFC` | page background |
| `--bg-card` | `#FFFFFF` | cards, panels |
| `--border-subtle` | `#E5E7EB` | card borders, dividers |
| `--text-primary` | `#0F172A` | headings, primary text |
| `--text-secondary` | `#64748B` | captions, labels |

### Dark marketing/auth theme
| Token | Hex (approx) | Use |
|---|---|---|
| `--bg-dark` | `#0B1220` / `#0F172A` | landing hero background, auth card background |
| `--text-on-dark` | `#FFFFFF` | headings on dark |
| `--text-on-dark-muted` | `#94A3B8` | body copy on dark |

## 3. Typography

- Clean geometric/humanist sans-serif (Inter, SF Pro, or system-ui
  equivalent).
- Strong weight hierarchy: bold, large headings (dashboard greeting,
  marketing hero) vs. medium-weight card titles vs. regular body/labels.
- Numeric KPI values are large and bold (e.g. "12,480", "96.4%") with a
  small label underneath and a small colored delta indicator
  ("↑ 2.4% vs last year").

## 4. Layout — App shell (dashboard, light theme)

**Structure:** fixed left sidebar (≈240px) + top bar + scrollable main
content + optional right-hand promo/insight panel on key screens.

**Left sidebar:**
- Logo top.
- Primary nav (icon + label): Home, Portfolio, Properties, Repairs,
  Compliance, Data & Uploads, Analytics, Reports, Ask DataLume.
- Active item: filled blue rounded-rect background, white icon/text.
- Divider, then secondary nav: Organisation, Users, Billing, Settings.
- Bottom-of-sidebar: a "Need help? Contact support" card, and an
  organisation switcher showing org name + property count (adaptive per
  the multi-tenant model — this is where org-switching for users with
  access to multiple orgs would live).

**Top bar:**
- Global search ("Search properties, repairs, compliance...") with a
  `⌘K` shortcut hint.
- Notification bell with unread dot.
- User menu: circular avatar (initials on solid color), name + role,
  chevron.

**Main content — Home / dashboard pattern:**
1. Greeting header ("Good morning, {name}") + subtext + a global date-range
   filter top-right.
2. A row of **KPI stat cards** (5–6 across on desktop): icon in a tinted
   rounded square, large bold value, label, small colored trend delta.
   Suggested Home KPIs: Total Properties, Compliance Rate, Open Repairs,
   Maintenance Spend, Data Health Score, Items Needing Attention.
3. A three-column analytical row:
   - A **trend line chart** (e.g. spend or volume over 12 months) with a
     hover tooltip showing the exact value/date, and a period-selector
     dropdown.
   - A **donut/ring chart** for a status breakdown (e.g. Compliance
     Overview: Compliant/Due Soon/Overdue/No Record) with a legend list of
     counts.
   - An **"Ask DataLume" panel**: sparkle icon + short description, a list
     of clickable suggested questions (each with a trailing arrow), and a
     text input with a circular send button pinned at the bottom.
4. A second row: a **regional/portfolio breakdown** (map or list with
   colored legend dots), a **"Requiring Attention" table** (thumbnail,
   address, issue count, priority badge, a "View" button), and a **Data
   Quality donut** with a breakdown of sub-metrics as horizontal progress
   bars (Completeness, Consistency, Uniqueness, Validity, Critical
   Fields).
5. A third row: a **Recent Uploads** table (filename, type, row count,
   status badge, relative upload time) and a **Top Risk Areas** horizontal
   bar list (domain name + colored percentage bar, red→amber→gray by
   severity).
6. A persistent **promo/insight card** in the right rail on key screens:
   dark navy card with a background photo, a short value-prop headline,
   a primary button, and a small italic tagline underneath.
7. Footer: legal/help links (Privacy, Terms, Security, Help Centre) plus
   the brand tagline, right-aligned.

**Card style:** white background, ~12–16px border radius, 1px subtle
border or very soft shadow (avoid heavy drop shadows), generous internal
padding (24px+).

**Status badges:** small pill shapes, colored background tint + colored
text (e.g. red-tinted pill for "High" priority, amber-tinted for
"Medium", green-tinted for "Processed").

## 5. Layout — Marketing + Auth (dark theme)

**Split-screen layout:**
- **Left panel** (dark, full-bleed background photo of a modern
  residential building at dusk, warm lit windows, subtle dark gradient
  overlay for text contrast):
  - Top nav (transparent, white text): Product, Solutions, Pricing,
    Resources, About; "Already have an account? Sign in" top-right on the
    marketing variant.
  - Large bold two-line headline + supporting paragraph.
  - Three small feature callouts in a row, each with an icon in a
    translucent rounded square + short label + one-line description
    (Upload / Understand / Act).
  - Primary CTA ("Start your free trial", solid blue, trailing arrow) +
    secondary CTA ("Book a demo", outline).
  - Reassurance checklist row (checkmark + short phrase): No credit card
    required, 14-day free trial, Cancel anytime.
  - A translucent testimonial card: quote mark, 1–2 sentence customer
    quote, attribution, and a small stats strip (e.g. properties
    analysed, faster reporting, higher accuracy).
  - "Trusted by" logo strip along the bottom.

- **Right panel** (solid dark card, slightly offset from the page edge,
  rounded corners):
  - "Welcome to DataLume" heading + short subtext.
  - Tab switcher: Sign In / Create Account (active tab underlined in
    blue).
  - Form fields with icon prefixes (mail icon for email, lock icon for
    password with a show/hide toggle), placeholder text.
  - "Forgot password?" link, right-aligned.
  - Full-width primary blue button.
  - "or continue with" divider, then two secondary OAuth buttons
    (Microsoft, Google) side by side, each with provider logo.
  - Switch-mode link at the bottom ("Don't have an account? Create one").
  - Trust badges row beneath the card (Secure / UK hosted / Built for
    housing), each icon + two-line micro-copy.
  - Brand tagline centered at the very bottom with a small blue
    underline accent.

## 6. Interaction & tone notes

- Enterprise-SaaS, not consumer-flashy: subtle motion only (hover states,
  soft transitions), no heavy animation.
- Every KPI/insight is paired with a trend indicator and, where relevant,
  a path to drill in ("View all →") — nothing is a dead end.
- Never communicate status via color alone (see accessibility
  requirements in `BUILD_PROMPT.md` §73) — pair color with icon and/or
  text label on every badge and trend indicator.
- The dark marketing/auth theme and the light app theme are two distinct,
  intentional modes — do not blend them (e.g. don't put the dark hero
  treatment inside the authenticated app shell).
