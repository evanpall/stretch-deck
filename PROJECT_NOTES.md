# Stretch Deck — Project Notes

Point Claude here at the start of a new session to catch up fast.

## What this is

A single-page, installable PWA for browsing and playing personal exercise/stretch
videos at the gym. No backend, no build step — `index.html` is HTML + CSS +
vanilla JS in one file.

- **Live app:** https://evanpall.github.io/stretch-deck/ (GitHub Pages, deployed
  straight from the `main` branch — no CI workflow, just push and it redeploys
  in roughly 30s–2min)
- **Repo:** https://github.com/evanpall/stretch-deck
- Installed on phone as a PWA (Add to Home Screen)

## Structure

- `index.html` — the entire app (markup, styles, and the JS app in one `<script>`
  block near the bottom)
- `manifest.json` — PWA manifest (icons, theme colors, start URL)
- `sw.js` — service worker: cache-first app shell, video files cached in a
  separate Cache Storage bucket
- `icon-*.png` — app icons
- `videos/<Category Folder>/*.mp4` — actual video files, one folder per
  category, matching `DEFAULT_CATEGORIES[].folder` in `index.html`. Videos are
  played straight from this path — nothing is uploaded or copied.

## How data flows (important — read before changing seed logic)

- `DEFAULT_CATEGORIES` and `SEED_EXERCISES` (both hardcoded arrays near the top
  of the `<script>` block in `index.html`) are the source-of-truth list of
  categories/videos as of the last time someone scanned the `videos/` folders.
- Actual runtime state (`state.categories/exercises/routines`) lives in
  **`localStorage`** per-browser, key `stretchdeck:v2`.
- On load: if `localStorage` already has data, the app loads it, then calls
  `mergeNewSeeds()` (added 2026-09-13) to pull in any `DEFAULT_CATEGORIES` /
  `SEED_EXERCISES` entries not already present by `id` and not previously
  deleted (tracked via `dismissedSeedIds`, also in localStorage). This is what
  makes a newly-added seed video show up on a phone that already ran the app
  before, without wiping the user's own edits/renames.
- Deleting a seed-origin exercise (`id` starting `seed-`) adds it to
  `dismissedSeedIds` so `mergeNewSeeds()` won't resurrect it.

## Workflow: adding a new video

1. Drop the `.mp4` into the right `videos/<Category>/` folder.
2. Add a matching entry to `SEED_EXERCISES` in `index.html` (id, category,
   `videoFile` = exact filename, placeholder title like
   `"Untitled clip N (rename me)"`).
3. **Bump `SHELL_CACHE` in `sw.js`** (e.g. `v3` → `v4`) — the service worker is
   cache-first for the app shell, so without bumping this, installed phones
   keep serving stale JS/HTML indefinitely. There's a comment in `sw.js`
   reminding of this.
4. Commit + push to `main`.
5. On the phone: fully close the installed app (swipe away, not just
   backgrounded) and reopen. May take two open/close cycles for the new
   service worker to fully take over — see the cache-first-refresh-in-background
   fetch handler in `sw.js`.
6. Open the new exercise on the phone and fill in the real title
   (`(rename me)` placeholders are meant to be renamed after watching the clip).

## Known gotchas

- Forgetting step 3 (bump `SHELL_CACHE`) is the most common cause of "I pushed
  it but my phone doesn't see it."
- `mergeNewSeeds()` only adds things by `id` — if you reuse a `seed-N` id for a
  different video, existing installs won't pick up the change (the id already
  "exists" for them). Always use a fresh, unused `seed-N` id for new entries.
- Videos are matched to categories via `DEFAULT_CATEGORIES[].folder`, which
  must exactly match the on-disk folder name (case/spacing sensitive — e.g.
  `"Warm-up- Strech"`, `"ISometric Stability"` are the real folder names,
  typos and all).

## Changelog (most recent first)

- **2026-09-26** — Added seed entries for two new videos: one in `videos/Back/`
  (`AQNepMF3h...zotQOxNRRYm71x9xI.mp4`) and one in `videos/Warm-up- Strech/`
  (`AQMD9GqiGV4Qg7...ZfpedHMjWGe-mlHZKZw.mp4`). Bumped `SHELL_CACHE` to `v7`.
- **2026-09-22** — Added seed entries for a new video that belongs to both
  Abductors and Core Rotation (`AQN707BV746tS...sIISSQ.mp4`, saved in both
  `videos/Abductors/` and `videos/Core Rotation/`). Bumped `SHELL_CACHE` to
  `v6`.
- **2026-09-15** — Added seed entry for a new Back video
  (`AQMC_7GM6a086...sIISSQ.mp4`). Bumped `SHELL_CACHE` to `v5`.
- **2026-09-13** — UI/UX pass after a mobile-viewport visual audit: collapsed the
  setup banner to a one-line summary with a "Show details" toggle, added a fade
  on the scrollable category-chip row, made exercise cards stack to one column
  under 480px (fixes placeholder titles wrapping under their action buttons),
  bumped icon buttons (gear, delete) from 32px to 44px for tap targets, made
  category cards a compact single-line row under 480px instead of tall cards,
  gave card/routine titles an explicit `color` instead of relying on the
  browser's native button-text default, and added a category-accent border
  around exercise videos. Bumped `SHELL_CACHE` to `v4`.
- **2026-09-13** — Added `mergeNewSeeds()` so new seed videos added to the code
  automatically appear for phones that already ran the app before (previously
  `SEED_EXERCISES` only applied on a true first run). Bumped `SHELL_CACHE` to
  `v3`. Root-caused a report of "added a video, don't see it on my phone" to
  this plus a missed cache-version bump on the prior seed-add commit.
- **2026-09-13** — Added seed entry for a new warm-up video
  (`AQPWYcMatwCwh_...mp4` in `Warm-up- Strech`).
- Earlier — Uploaded more video files; simplified home navigation so
  categories can jump directly to each other; turned the app into an
  installable, offline-capable PWA (manifest + service worker + video caching).
