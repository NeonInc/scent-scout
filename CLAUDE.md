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
- The Neon Inc account badge is placed in `#acct` (top-right of the bar) and restyled from this page
  with `.acct .nc-badge`. Don't edit `neon-cloud.js` from here.
- Design: iOS-style. System font, grey grouped lists, one tint colour (`--tint`), bottom tab bar
  (Discover / Search / Watchlist) and a detail sheet for each fragrance. Keep new UI in that style.
- ARC prices come from each product page's structured data, read within a time budget per run and
  remembered in `data/product_pages.json` (see `collect_dynamicweb`).
