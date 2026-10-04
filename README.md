# Scent Scout

Finds the cheapest price for a fragrance across South African stores, with delivery included.

**Stores:** Panda Perfumes, Rio Perfumes, Dubai Perfume Café, Edgars and Bash. Only authorised retailers and specialist perfume shops, no marketplaces.

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
- If there's still no size, but another store lists the same fragrance at exactly the same price, that size is used. These show a **Size matched by price** badge.
- If no size can be found, the dearer of a store's unsized listings for that fragrance is assumed to be the 100 ml. A single unsized listing is also assumed to be 100 ml. These show a **Size guessed** badge.
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

## Stores that can't be added automatically

These were checked from GitHub Actions on 2026-10-04:

- **Superbalist and Dis-Chem** show a Cloudflare "checking your browser" page to automated visitors. They block on purpose, so they aren't collected. Each fragrance on the site links to their search instead (*Also check*).
- **Clicks** loads its product list through a third-party search service (Algolia) rather than in the page. It could be added by querying that service; it's left out for now.
- **Truworths** blocks automated requests.
- **Woolworths** loads products through its own API after the page loads. Not investigated further yet.
- Marketplaces (Takealot, Amazon, Makro) are left out on purpose: third-party sellers make fakes too likely.

To check a new store, add its URL to `tools/probe_targets.json` and run **Actions → Probe stores**. The raw responses land on the `probe` branch.

## Notes

- The collector waits about a second between requests and identifies itself in its User-Agent.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. The price commits normally count as activity.
