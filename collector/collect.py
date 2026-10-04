#!/usr/bin/env python3
"""Scent Scout collector.

Reads every store in stores.json, turns its products into one common format and writes
docs/data/prices.json for the website. Runs on GitHub Actions on a schedule.

If one store fails, the others still update and that store keeps its last good prices
(marked as stale) instead of disappearing from the site.
"""
import datetime as dt
import json
import re
import sys
import time
import traceback
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import normalize as N  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "collector" / "stores.json"
OUT = ROOT / "docs" / "data" / "prices.json"
HISTORY = ROOT / "data" / "history.json"

UA = "ScentScout/1.0 (personal price comparison; +https://github.com/NeonInc/scent-scout)"
DELAY = 1.2          # seconds between requests to the same store, to stay polite
MAX_VARIATIONS = 300  # cap on extra WooCommerce variation lookups per run

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.5"})


def log(*a):
    print(*a, flush=True)


def get(url, params=None, as_json=True):
    last = None
    for attempt in range(3):
        try:
            r = session.get(url, params=params, timeout=40)
            time.sleep(DELAY)
            if r.status_code in (200, 206):
                return r.json() if as_json else r.text
            last = f"HTTP {r.status_code}"
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(6 * (attempt + 1))
                continue
            break
        except requests.RequestException as e:
            last = str(e)
            time.sleep(6 * (attempt + 1))
    raise RuntimeError(f"{last} for {url}")


def money(v):
    try:
        f = float(v)
        return round(f, 2) if f > 0 else None
    except (TypeError, ValueError):
        return None


def with_width(src, w=300):
    """Shopify CDN image at a small width, without the cache-buster query."""
    if not src:
        return ""
    return re.sub(r"^https?:", "", src.split("?")[0]) + f"?width={w}"


def small_img(src):
    """Any other store image: drop the query string; VTEX images get resized to 300px."""
    if not src:
        return ""
    src = re.sub(r"^https?:", "", src.split("?")[0])
    return re.sub(r"(/arquivos/ids/\d+)/", r"\1-300-300/", src)


def make_listing(store, *, pid, title, brand_raw, price, was, stock, url, img,
                 variant_text="", desc_text="", tags_text="", deal=""):
    brand = N.norm_brand(brand_raw, title)
    full = f"{title} {variant_text}".strip()
    kind = N.kind_of(title, tags_text, variant_text)
    # Size: the variant/title first ("listed"), then the description ("description").
    sizes = N.sizes_in(variant_text) or N.sizes_in(title)
    ml, ms = (sizes[0], "l") if sizes else (None, None)
    if ml is None and kind == "p" and desc_text:
        d = N.size_from_description(desc_text)
        if d:
            ml, ms = d, "d"
    li = {
        "id": f"{store['id']}-{pid}",
        "s": store["id"],
        "b": brand,
        "n": N.display_name(title, brand),
        "t": title.strip(),
        "k": N.group_key(brand, title),
        "c": N.concentration(full, (desc_text or "")[:300], tags_text),
        "ml": ml,
        "ms": ms,
        "kd": kind,
        "g": N.gender_of(title, tags_text),
        "p": price,
        "w": was if was and price and was > price + 0.5 else None,
        "st": 1 if stock else 0,
        "u": url[len(store["url"]):] if url.startswith(store["url"]) else url,
        "i": img,
    }
    ib = N.inspired_by(title, desc_text)
    if ib:
        li["ib"] = ib
    if deal:
        li["dl"] = deal
    return {k: v for k, v in li.items() if v not in (None, "") or k in ("p", "st")}


# ---------- Shopify (Panda, Rio, Edgars) ----------

def deal_from_tags(tags):
    t = " ".join(tags).lower()
    if "buy2get" in t or "take2" in t or "take 2" in t:
        return "Multi-buy deal on site"
    return ""


def collect_shopify(store):
    out, seen = [], set()
    for path in store["paths"]:
        page = 1
        while page <= 60:
            data = get(store["url"] + path, params={"limit": 250, "page": page})
            products = data.get("products", [])
            if not products:
                break
            for p in products:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                title = p.get("title", "")
                tags = p.get("tags") or []
                if isinstance(tags, str):
                    tags = [x.strip() for x in tags.split(",")]
                ptype = p.get("product_type") or ""
                hay = f"{title} {ptype} {' '.join(tags)}"
                if N.is_excluded(title) or (store.get("filter_fragrance") and not N.looks_like_fragrance(hay)):
                    continue
                desc = N.strip_html(p.get("body_html", ""))
                images = p.get("images") or []
                base_img = images[0]["src"] if images else ""
                for v in p.get("variants", []):
                    price = money(v.get("price"))
                    if not price:
                        continue
                    vt = v.get("title") or ""
                    if vt.lower() == "default title":
                        vt = ""
                    img = (v.get("featured_image") or {}).get("src") or base_img
                    out.append(make_listing(
                        store, pid=v["id"], title=title, brand_raw=p.get("vendor", ""),
                        price=price, was=money(v.get("compare_at_price")), stock=v.get("available", True),
                        url=f"{store['url']}/products/{p['handle']}" + (f"?variant={v['id']}" if len(p.get("variants", [])) > 1 else ""),
                        img=with_width(img), variant_text=vt, desc_text=desc,
                        tags_text=f"{ptype} {' '.join(tags)}", deal=deal_from_tags(tags),
                    ))
            log(f"  {store['id']} {path} page {page}: {len(products)} products")
            if len(products) < 250:
                break
            page += 1
    return out


# ---------- WooCommerce Store API (Dubai Perfume Café) ----------

def woo_price(prices, key):
    if not prices or prices.get(key) in (None, ""):
        return None
    unit = int(prices.get("currency_minor_unit", 2))
    return money(int(prices[key]) / (10 ** unit))


def collect_woocommerce(store):
    api = store["url"] + "/wp-json/wc/store/v1/products"
    excluded = set(store.get("exclude_categories", []))
    out, lookups, page = [], 0, 1
    while page <= 80:
        products = get(api, params={"per_page": 100, "page": page})
        if not products:
            break
        for p in products:
            cats = p.get("categories") or []
            if any(c.get("slug") in excluded for c in cats):
                continue
            title = N.strip_html(p.get("name", ""))
            if N.is_excluded(title):
                continue
            brands = p.get("brands") or []
            brand_raw = brands[0]["name"] if brands else ""
            base = N._remove_inspired(title)
            if not brand_raw and " by " in base.lower():
                brand_raw = base.lower().split(" by ")[-1].split("(")[0].strip(" -–")
            cat_text = " ".join(c.get("name", "") for c in cats)
            desc = N.strip_html((p.get("short_description") or "") + " " + (p.get("description") or ""))
            img = (p.get("images") or [{}])[0].get("thumbnail") or (p.get("images") or [{}])[0].get("src", "")
            rows = []
            if p.get("type") == "variable" and p.get("variations") and lookups < MAX_VARIATIONS:
                for var in p["variations"]:
                    if lookups >= MAX_VARIATIONS:
                        break
                    lookups += 1
                    try:
                        vd = get(f"{api}/{var['id']}")
                    except RuntimeError as e:
                        log(f"  variation {var['id']} failed: {e}")
                        continue
                    vt = " ".join(a.get("value", "") for a in var.get("attributes", []))
                    rows.append((var["id"], vt, vd.get("prices"), vd.get("is_in_stock", True)))
            else:
                rows.append((p["id"], "", p.get("prices"), p.get("is_in_stock", True)))
            for vid, vt, prices, stock in rows:
                price = woo_price(prices, "price")
                if not price:
                    continue
                regular = woo_price(prices, "regular_price")
                out.append(make_listing(
                    store, pid=vid, title=title, brand_raw=brand_raw, price=price, was=regular,
                    stock=stock, url=p.get("permalink", store["url"]), img=small_img(img),
                    variant_text=vt, desc_text=desc, tags_text=cat_text,
                ))
        log(f"  {store['id']} page {page}: {len(products)} products")
        if len(products) < 100:
            break
        page += 1
    return out


# ---------- VTEX (Bash) ----------

def collect_vtex(store):
    api = store["url"] + "/api/catalog_system/pub/products/search"
    out, seen = [], set()
    for path in store["paths"]:
        start = 0
        while start < 2500:
            products = get(api + path.split("?")[0], params={**dict(
                kv.split("=") for kv in path.split("?")[1].split("&")), "_from": start, "_to": start + 49})
            if not products:
                break
            for p in products:
                title = p.get("productName", "")
                if N.is_excluded(title):
                    continue
                cats = " ".join(p.get("categories") or [])
                desc = N.strip_html(p.get("description", ""))
                for it in p.get("items", []):
                    if it["itemId"] in seen:
                        continue
                    seen.add(it["itemId"])
                    sellers = it.get("sellers") or []
                    if not sellers:
                        continue
                    offer = sellers[0].get("commertialOffer", {})
                    price = money(offer.get("Price"))
                    if not price:
                        continue
                    # Bash puts the bottle size in its own "Size" field; fall back to the item name.
                    vt = " ".join(str(x) for x in (it.get("Size") or []))
                    if not N.sizes_in(vt):
                        vt = " ".join(str(x) for x in (it.get("name"), it.get("nameComplete")) if x)
                    sizes = N.sizes_in(vt)
                    if sizes and len(set(sizes)) == 1:
                        vt = f"{sizes[0]}ml"
                    elif not sizes:
                        vt = ""
                    imgs = it.get("images") or []
                    out.append(make_listing(
                        store, pid=it["itemId"], title=title, brand_raw=p.get("brand", ""),
                        price=price, was=money(offer.get("ListPrice")),
                        stock=offer.get("IsAvailable", (offer.get("AvailableQuantity") or 0) > 0),
                        url=p.get("link", store["url"]) + (f"?skuId={it['itemId']}" if len(p.get("items", [])) > 1 else ""),
                        img=small_img(imgs[0].get("imageUrl", "")) if imgs else "",
                        variant_text=vt, desc_text=desc, tags_text=cats,
                    ))
            log(f"  {store['id']} {path} from {start}: {len(products)} products")
            if len(products) < 50:
                break
            start += 50
    return out


COLLECTORS = {"shopify": collect_shopify, "woocommerce": collect_woocommerce, "vtex": collect_vtex}


# ---------- history (lowest seen, recent drops) ----------

def update_history(listings, today):
    hist = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    for li in listings:
        if li.get("stale"):
            continue
        h = hist.get(li["id"])
        p = li["p"]
        if not h:
            hist[li["id"]] = {"low": p, "lowd": today, "last": p, "first": today, "seen": today}
            continue
        h["seen"] = today
        if p != h["last"]:
            h["prev"], h["last"], h["chg"] = h["last"], p, today
        if p < h["low"]:
            h["low"], h["lowd"] = p, today
    for li in listings:
        h = hist.get(li["id"])
        if not h:
            continue
        for f in ("lo", "lod", "ls", "pv"):
            li.pop(f, None)
        if h["low"] < li["p"] - 0.5:
            li["lo"], li["lod"] = h["low"], h["lowd"]
        elif (dt.date.fromisoformat(today) - dt.date.fromisoformat(h.get("first", today))).days > 7:
            li["ls"] = 1  # at the lowest price we've recorded, and we've watched it over a week
        if h.get("prev") and h.get("chg") and h["prev"] > li["p"]:
            days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(h["chg"])).days
            if days <= 14:
                li["pv"] = h["prev"]
    # Forget listings that haven't been seen for 90 days so the file doesn't grow forever.
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=90)).isoformat()
    hist = {k: v for k, v in hist.items() if v.get("seen", today) >= cutoff}
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(hist, separators=(",", ":"), sort_keys=True))


def main(only=None):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    previous = json.loads(OUT.read_text()) if OUT.exists() else {"listings": [], "stores": []}
    prev_by_store = {}
    for li in previous.get("listings", []):
        prev_by_store.setdefault(li["s"], []).append(li)
    prev_status = {s["id"]: s for s in previous.get("stores", [])}

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    today = now.astimezone(dt.timezone(dt.timedelta(hours=2))).date().isoformat()
    all_listings, stores_out = [], []

    for store in cfg["stores"]:
        if only and store["id"] not in only:
            all_listings += prev_by_store.get(store["id"], [])
            stores_out.append(prev_status.get(store["id"], {"id": store["id"], "name": store["name"]}))
            continue
        log(f"Collecting {store['name']}…")
        info = {k: store[k] for k in ("id", "name", "url", "delivery")}
        try:
            items = COLLECTORS[store["platform"]](store)
            if not items:
                raise RuntimeError("no products found")
            info.update(status="ok", count=len(items), updated=now.isoformat())
            all_listings += items
            log(f"  -> {len(items)} listings")
        except Exception as e:  # keep going with the other stores
            traceback.print_exc()
            old = prev_by_store.get(store["id"], [])
            for li in old:
                li["stale"] = True
            all_listings += old
            info.update(status="error", error=str(e)[:200], count=len(old),
                        updated=prev_status.get(store["id"], {}).get("updated"))
            log(f"  !! {store['name']} failed: {e} (kept {len(old)} old listings)")
        stores_out.append(info)

    fresh = [li for li in all_listings if not li.get("stale")]
    N.infer_sizes_by_price(fresh)
    N.apply_size_assumptions(fresh)
    update_history(all_listings, today)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated": now.isoformat(), "stores": stores_out, "listings": all_listings},
                              ensure_ascii=False, separators=(",", ":")))
    ok = sum(1 for s in stores_out if s.get("status") == "ok")
    log(f"Done: {len(all_listings)} listings, {ok}/{len(stores_out)} stores updated.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
