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
