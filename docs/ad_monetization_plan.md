# Ad monetization plan

*Written 2026-07-17. Decision: run tasteful display ads (no gambling ads) via
Google AdSense now, treat it as pipeline-building rather than income, and
revisit premium networks / a paid ad-free tier as traffic grows.*

## Where we are

- Traffic: under 5k pageviews/month, much of it bot noise (see
  `docs/traffic_lab.md`). No client-side analytics yet — CloudFront logs via
  Athena only, which ad networks do not accept as proof of traffic.
- Audience: expected mostly US/Canada, with a Japanese-language variant of
  every page.
- Site: static Next.js export on S3+CloudFront (`web/`). No privacy policy,
  consent banner, or ads.txt existed before this work.

## Pros and cons of display ads

**Pros**

- Passive revenue with no payment infrastructure, no user accounts.
- Forces the legal/privacy plumbing (privacy policy, consent, analytics) that
  a future paid tier needs anyway.
- AdSense has no traffic minimum, so we can start now and accumulate account
  history + analytics history for later network applications.

**Cons**

- At current traffic, expect **$2–20/month**. Sports-content AdSense RPM is
  roughly $1–5; premium networks pay several times that but are gated on
  traffic we don't have. AdSense pays out at $100 accrued — the first payment
  could be a year away.
- Page-weight and layout-shift cost on a deliberately fast static site.
  Mitigated by fixed-height ad containers and loading scripts async.
- Compliance overhead: Google requires a certified consent message for
  EEA/UK **and Canada** traffic; we ship Consent Mode v2 defaults and use
  Google's built-in Privacy & messaging CMP.
- Gambling-adjacency classification risk (below) can reduce demand on some
  pages.
- Badly placed ads would undercut a portfolio-quality site. Placement is
  deliberately sparse: one leaderboard under the header, one unit above the
  footer, nothing mid-table, nothing on the advisor form, Auto ads off.

## Gambling-adjacency assessment

`/accuracy` and `/performance` benchmark against the betting market's closing
line and show an against-the-spread record. Assessment: **low-to-moderate
risk, no content changes needed.**

- Only *completed* games are graded; there are no odds for upcoming games, no
  sportsbook links, no affiliate CTAs, and "not betting advice" disclaimers
  appear in both languages.
- Under Google Publisher Policies, gambling-related content is a
  **restriction**, not a prohibition: the realistic worst case is Google's own
  demand declining to bid on those pages (lower revenue there), not account
  suspension.
- The one thing a classifier could trip on is that the site publishes
  predicted margins for tonight's games (pattern-matches "sports picks").
  Honest framing and historical-only spreads are the right mitigations.
- Actions taken/planned: block the **Gambling & Betting** sensitive category
  in AdSense (we never show gambling ads regardless of classification); if
  review flags `/accuracy` or `/performance`, exclude ad units from just those
  routes (the `AdSlot` component supports route exclusion).

## Network comparison and growth gates

| Network | Minimum | Notes |
|---|---|---|
| **Google AdSense** | none | Start here. Lower RPM, instant eligibility, full category blocking. Auto ads OFF. |
| Ezoic | none | Higher RPM than AdSense but heavy scripts and pushy placements; poor fit for a fast, tasteful site. Skip. |
| **Mediavine Journey** | ~10k sessions/mo (GA required) | First real upgrade gate. Apply when GA4 shows sustained 10k sessions. |
| Mediavine (full) / Raptive | 50k sessions / 100k PV | The actual money. Sports content RPMs commonly $10–30. Long-term gate. |

Premium networks require **Google Analytics history**, which is why GA4 goes
in now even though CloudFront/Athena already measures traffic internally.

**Gates:**

1. Now → AdSense + GA4 + consent + privacy page (this work).
2. Sustained ~10k sessions/mo in GA4 → apply to Mediavine Journey, drop
   AdSense if accepted.
3. 50k+ sessions/mo → full Mediavine or Raptive.
4. Real repeat-user base → consider the paid ad-free tier (below).

**What to watch** (monthly, low effort): AdSense RPM by page, GA4 sessions,
CLS in Core Web Vitals (ads are the usual culprit; our fixed-height containers
should keep it ~0).

## Implementation (what's in the repo)

- `web/app/layout.tsx` — Consent Mode v2 defaults (denied in EEA/UK/CH/CA,
  granted elsewhere), GA4 loader, AdSense loader. Both gated on
  `NEXT_PUBLIC_GA_ID` / `NEXT_PUBLIC_ADSENSE_CLIENT` build-time env vars: unset
  → nothing renders, so the site is byte-identical to before until the IDs are
  filled in `.github/workflows/frontend.yml`.
- `web/components/AdSlot.tsx` — fixed-min-height ad container (no layout
  shift), small "Ad"/「広告」 label, route-exclusion list, collapses only when
  ads are disabled entirely.
- `web/app/privacy/` — bilingual privacy policy; linked from the footer.
- `web/public/ads.txt` — placeholder comment; real `google.com, pub-…` line
  goes in after AdSense approval.

## Manual steps (Kai)

Tracked at the bottom of this doc so they survive the session:

1. Create a GA4 property for hoopmodel.com → put the `G-…` id in
   `frontend.yml` as `NEXT_PUBLIC_GA_ID`.
2. Create an AdSense account, add hoopmodel.com, choose the "code snippet"
   verification → put the `ca-pub-…` id in `frontend.yml` as
   `NEXT_PUBLIC_ADSENSE_CLIENT` (the loader in `layout.tsx` doubles as the
   verification snippet). Push, then request review.
3. In AdSense **Privacy & messaging**: enable the GDPR message (EEA/UK) and
   the Canada message. This is Google's certified CMP; it updates the Consent
   Mode defaults we ship.
4. In AdSense **Brand safety → Blocking controls**: block *Gambling &
   Betting* (plus anything else unwanted — dating, get-rich-quick, politics
   are common blocks). Turn **Auto ads OFF** for the site.
5. After approval: copy the ads.txt line AdSense shows into
   `web/public/ads.txt`, create two display ad units (leaderboard +
   footer), and put their slot ids into the two `<AdSlot/>` usages.

## Paid ad-free tier (explicitly deferred)

Not built now. Sketch for when there's a real user base: Cognito or
email-magic-link auth, Stripe subscription (~$2–3/mo), a `subscriber` flag the
static site checks client-side to suppress `AdSlot` rendering. Only worth the
maintenance once ad revenue per user is meaningful — i.e. after the premium
network gate, not before.

## AdSense rejection #1 and fixes (2026-10-27)

### Diagnosis

The first review came back with the generic 「AdSense の申請を修正」 email. It
names no specific reason; its only hint is the tip that insufficient content
quantity/quality is the common cause (in practice, "Low value content").
Fetching every page the way a crawler sees it confirmed that:

- The static export prerendered almost nothing: every data page fetched its
  content client-side, so `/accuracy` was 45 words ("Loading the track
  record…") and most pages were 72–156 words of nav + footer.
- 9 of 11 pages shared one `<title>` and meta description.
- No sitemap and no contact page.

Ruled out: AdSense verification (loader + `ca-pub` in `<head>`), ads.txt
(correct pub line), robots.txt (allows all). Duplicate-account check is Kai's.
(An early worry that `/ja` was a broken link was wrong: the 日本語 toggle is a
button, not a link.)

### Fixes shipped (commit 27216fd, deployed 2026-10-27)

- **Build-time data bake** (`web/lib/serverData.ts`): `/` (latest slate +
  proof bar), `/players` (latest slate) and `/accuracy` (12-month per-model
  summary, written as prose) fetch the API during `next build`. The client still
  refreshes on mount; an API outage never fails the build.
- **Daily rebuild**: `frontend.yml` also runs at 23:30 UTC (after the 5:45pm
  ET pre-tip refresh) so the bake stays current; `workflow_dispatch` added.
  GitHub disables scheduled workflows after 60 days without repo activity.
- **Page guides** (`web/lib/pageGuides.ts`, `<PageGuide/>`): a bilingual
  "how to read this page" essay at the foot of every data page.
- **Per-page metadata**: `%s — HoopModel` title template, unique descriptions,
  canonical URLs. Pages split into server `page.tsx` + client `*Content.tsx`.
- **`/sitemap.xml`** (`app/sitemap.ts`) + `Sitemap:` line in robots.txt.
- **`/contact`** page (bilingual, footer link) showing `contact@hoopmodel.com`.

Result on production: prerendered text went from 45–156 words to ~300–675
words per page.

### Email + Search Console (infra, commits 27216fd / cfcc04a)

- `infra/email.tf`: ImprovMX MX records (`mx1`/`mx2.improvmx.com`) + apex TXT
  record set. Applied by Kai with `-target`; forwarding verified with a test
  email 2026-10-27. Replies go out from Gmail (ImprovMX SMTP is paid).
- Route 53 allows **one TXT record set per name**, so every apex TXT value
  (SPF, `google-site-verification=…`) lives in the `apex_txt_values` list in
  `email.tf`. Never add a second TXT resource for the apex.
- Search Console: Domain property for hoopmodel.com, verified via that TXT
  value. Submit the sitemap as the full URL
  `https://hoopmodel.com/sitemap.xml` (Domain properties need the full URL,
  unlike URL-prefix properties).

### Articles section (2026-10-27)

Original written analysis is the strongest content signal, so the site now has
`/articles` with four English posts drawn from the experiment reports
(signal vs noise, the margin-error floor, impact ratings, playoff
predictability). Japanese readers see the translated titles/summaries and an
"English only for now" notice. Ideas backlog, disclosure rules and
publication log: **`docs/articles.md`**. Same batch: Japanese page names in the
page guides and contact page aligned with the actual nav labels.

### Remaining steps (Kai)

1. Check Search Console → Sitemaps shows **Success** (12+ pages; it can say
   "Couldn't fetch" for the first hours), and optionally *Request indexing*
   for `/`, `/accuracy/`, `/players/`, `/articles/`.
2. Keep publishing: Japanese versions of the four articles, plus one or two
   more from `docs/articles.md` before re-review.
3. **Around mid-to-late November 2026**: confirm Search Console → Pages shows
   the pages indexed, then AdSense → 「申請内容を見直す」 → request review.
4. If rejected again, check AdSense → Sites / Policy center for a named
   reason before changing anything else.
