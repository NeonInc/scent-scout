# Notes for Claude: scent-scout

Scent Scout is live at https://neoninc.github.io/scent-scout/ (GitHub Pages from the `docs/`
folder) and is one tile on the Neon Inc hub (https://neoninc.github.io/, repo
`NeonInc/neoninc.github.io`).

- The website is `docs/index.html`. Keep it in `docs/` and don't rename the repo: the hub
  tile and people's home-screen shortcuts point at `/scent-scout/`.
- A GitHub Action commits new prices twice a day. Before pushing, pull first
  (`git pull --rebase`) so you don't clash with a price commit.
- The hub reads the watchlist key `scentscout.watch2` (read-only) to show "N on your
  watchlist". Don't rename that key. If its shape changes, update `STATS.scent` in the
  hub's `index.html` too.
- Don't change the hub or other apps from here. They live in their own repos.

- Cloud saves: the watchlist syncs through the shared `/neon-cloud.js` (hub repo) for signed-in
  people. Use `saveWatch()` for changes the person makes (it syncs) and `saveWatch(true)` for
  automatic tidy-ups like price bookkeeping (stays on the device).
- Sign-in lives in the Profile sheet (round button top-right, `#profilebtn`), built from
  `NeonCloud.user()`, `signIn()`, `signOut()` and `onStatus()`. `neon-cloud.js` loads `async`;
  `initCloud()` runs when it arrives. Don't edit `neon-cloud.js` from here.
- Email alerts are a sign-up list only for now: each person's choice is saved in their own account
  at `users/{uid}/alerts/scent` (`enabled`, `email`, `minDrop`, `status: "pending"`). Nothing sends
  email yet. Before sending, update the hub's `privacy.html` (new use of email addresses).
- Looks: `localStorage['scentscout.theme']` = auto | light | dark (graphite) | love, set on `<html data-theme>`
  by an inline script in `<head>` so there's no flash. Keep new colours as CSS variables per theme.
- `docs/sw.js` keeps an offline copy (page + prices) and refreshes it in the background. If you add
  files the page needs offline, add them to `SHELL`; bump `CACHE` only to throw away old copies.
- `prices.json` is compacted by the collector (`compact()`/`expand()`): image addresses share a
  per-store start/end (`stores[].img`), titles equal to the name are dropped, and profiles use the
  `phrases`/`notes` tables. The page expands these in `prepare()`.
- Design: iOS-style. System font, grey grouped lists, one tint colour (`--tint`), bottom tab bar
  (Discover / Search / Watchlist) and a detail sheet for each fragrance. Keep new UI in that style.
- ARC prices come from each product page's structured data, read within a time budget per run and
  remembered in `data/product_pages.json` (see `collect_dynamicweb`).
