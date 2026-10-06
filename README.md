# Scent Scout

Finds the cheapest price for a fragrance across South African stores, with delivery included.

**Stores:** Panda Perfumes, Rio Perfumes, Dubai Perfume Café, Edgars, Bash (which also covers Foschini and Markham) and ARC. Only authorised retailers and specialist perfume shops, no marketplaces.

## How it works

1. `collector/collect.py` reads each store's public product feed twice a day:
   - Shopify feeds (`/products.json`): Panda, Rio and Edgars
   - The WooCommerce store API: Dubai Perfume Café
   - The VTEX catalogue API: Bash
   - ARC's Dynamicweb product feed: the JSON its own category pages load. It lists each product once, at its default size.
2. It writes every fragrance listing to `docs/data/prices.json`. Each listing has a brand, name, size, concentration, price, "was" price, stock and link.
3. GitHub Actions runs this on a schedule (`.github/workflows/update-prices.yml`) and commits the new prices.
4. `docs/index.html` is the website. It's a single page that loads `prices.json` and does the search and comparison in the browser.

## Matching and sizes

- The same fragrance from different stores is grouped by brand plus a cleaned-up name. Size, concentration words, "for men" and "inspired by …" tails are stripped first. Brand spellings are mapped in `collector/brands.json`.
- Size comes from the variant or title, then from the top of the description.
- If there's still no size, but another store lists the same fragrance at exactly the same price, that size is used. These show a **Size matched by price** badge.
- If no size can be found, the dearer of a store's unsized listings for that fragrance is assumed to be the 100 ml. A single unsized listing is also assumed to be 100 ml. These show a **Size guessed** badge.
- `data/history.json` keeps each listing's lowest price, which powers the "Was R… on …" and "Lowest we've seen" badges.

## Scent profiles ("Smells like")

`collector/scent.py` reads the notes each store lists in its product description (for example bergamot, vanilla or oud), plus any scent-family words ("a Woody Spicy fragrance", "Profile: Floral • Fruity"). Only the note names are used, never the store's own text. The notes become:

- **Scent families:** Citrusy, Fresh & airy, Green vibes, Herbal, Floral, Fruity, Sweet, Spicy, Woody, Oud, Warm & ambery, Leathery & smoky, Clean & musky, Boozy.
- **Seasons and time of day:** for example "🌸 Spring" and "Daytime".
- **A short "smells like" line:** for example "a summer day at the beach: zesty citrus and sea air".

Each note counts once per store, so one store with many variants doesn't skew the result. Fragrances need at least three notes to get a profile.

- **"Inspired by":** clones that say what they're inspired by show "Smells like Creed Aventus".
- **"Often compared to":** a few widely made comparisons are added by hand in `collector/scent_overrides.json`.

**Ratings:** Fragrantica's terms of service forbid scraping and automated access, allow their content for personal non-commercial use only, and offer no public API. So the site doesn't copy their ratings; each fragrance links to its Fragrantica reviews instead.

## Discover and the watchlist

- **Discover (home page):** quick picks (season, scent family, under R500, for him or her, designer alternatives) and rails:
  - biggest price drops
  - in season now
  - designer smell for less
  - same bottle, big price difference between stores
  - lowest prices we've seen
- **Designer and clone pairs:** worked out in the browser by matching a clone's "inspired by" text to a designer fragrance's brand and name.
- **Watchlist:** saved in the visitor's browser only (localStorage). It records the price and bottle size when a fragrance is saved, and flags a drop for the same size on the next visit. Email alerts would need a small backend, so they're left for later.
- **Watchlist backup:** Watchlist → *Back up or move your watchlist*. It works like Neon Arcade's save codes:
  - **Save code** (`SS1-<checksum>-<data>`): the watchlist as JSON in URL-safe base64. The checksum catches codes that were cut off when copying.
  - **Share link** (`?view=watchlist#import=SS1-…`): opening it on any device offers *Add to mine* or *Replace mine*. The code sits after the `#`, so it never reaches the server.
  - **Backup file:** a `.txt` with the code in it, which *Load backup file* reads back.
  - **Contents:** codes only contain fragrance keys, names, bottle sizes, saved prices and dates.

## Delivery fees

These are set in `collector/stores.json`. They were checked on 2026-10-04:

| Store | Fee | Free from |
|---|---|---|
| Panda Perfumes | R120 | R2,000 |
| Rio Perfumes | R99 | R1,000 |
| Dubai Perfume Café | R100 (estimate, not published) | R2,000 |
| Edgars | R75 | R750 |
| Bash | R60 | R650 |
| ARC | R60 | R750 |

## Common tasks

- **Run the prices now:** Actions → *Update prices* → *Run workflow*.
- **Add a brand spelling:** add it to `collector/brands.json`.
- **Add an "often compared to" line:** add it to `collector/scent_overrides.json`.
- **Change a delivery fee:** edit `collector/stores.json`.
- **Run tests locally:** `python tests/test_collector.py` (offline, no network needed).

## Stores that can't be added automatically

These were checked from GitHub Actions on 2026-10-04:

- **Superbalist and Dis-Chem** show a Cloudflare "checking your browser" page to automated visitors. They block on purpose, so they aren't collected. Each fragrance on the site links to their search instead (*Also check*).
- **Clicks** loads its product list through a third-party search service (Algolia) rather than in the page. It could be added by querying that service; it's left out for now.
- **Truworths** blocks automated requests.
- **Skins Cosmetics** (checked 2026-10-05) answers every automated request, robots.txt included, with a Cloudflare block. It would need their permission or a feed.
- **Woolworths** loads products through its own API after the page loads. Not investigated further yet.
- Marketplaces (Takealot, Amazon, Makro) are left out on purpose: third-party sellers make fakes too likely.

To check a new store, add its URL to `tools/probe_targets.json` and run **Actions → Probe stores**. The raw responses land on the `probe` branch.

## Notes

- The collector waits about a second between requests and identifies itself in its User-Agent.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. The price commits normally count as activity.
- GitHub runs scheduled workflows on a best-effort basis and can delay or drop them when it's busy. Backup check-ins run every two hours after each main run (07:43–11:43 and 19:43–23:43 SAST) and only collect when the prices are more than 10 hours old.

---

Scent Scout · NEON INC™ © 2026. All rights reserved.
