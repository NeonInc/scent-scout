# Scent Scout

Finds the cheapest price for a fragrance across South African stores, with delivery included.

**Stores:** Panda Perfumes, Rio Perfumes, Dubai Perfume Café, Edgars and Bash.

## How it works

1. `collector/collect.py` reads each store's public product feed twice a day:
   - Shopify feeds (`/products.json`): Panda, Rio and Edgars
   - The WooCommerce store API: Dubai Perfume Café
   - The VTEX catalogue API: Bash
2. It writes every fragrance listing to `docs/data/prices.json`. Each listing has a brand, name, size, concentration, price, "was" price, stock and link.
3. GitHub Actions runs this on a schedule (`.github/workflows/update-prices.yml`) and commits the new prices.
4. `docs/index.html` is the website. It's a single page that loads `prices.json` and does the search and comparison in the browser.

## Matching and sizes

- The same fragrance from different stores is grouped by brand plus a cleaned-up name. Size, concentration words, "for men" and "inspired by …" tails are stripped first. Brand spellings are mapped in `collector/brands.json`.
- Size comes from the variant or title, then from the top of the description.
- If no size is listed anywhere, the dearer of a store's unsized listings for that fragrance is assumed to be the 100 ml. A single unsized listing is also assumed to be 100 ml. These show a **Size guessed** badge.
- `data/history.json` keeps each listing's lowest price, which powers the "Was R… on …" and "Lowest we've seen" badges.

## Delivery fees

These are set in `collector/stores.json`. They were checked on 2026-10-04:

| Store | Fee | Free from |
|---|---|---|
| Panda Perfumes | R120 | R2,000 |
| Rio Perfumes | R99 | R1,000 |
| Dubai Perfume Café | R100 (estimate, not published) | R2,000 |
| Edgars | R75 | R750 |
| Bash | R60 | R650 |

## Common tasks

- **Run the prices now:** Actions → *Update prices* → *Run workflow*.
- **Add a brand spelling:** add it to `collector/brands.json`.
- **Change a delivery fee:** edit `collector/stores.json`.
- **Run tests locally:** `python tests/test_collector.py` (offline, no network needed).

## Notes

- The collector waits about a second between requests and identifies itself in its User-Agent.
- Truworths blocks automated requests, so it isn't included. Superbalist has no product feed; it's the next store to add.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. The price commits normally count as activity.
