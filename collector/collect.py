#!/usr/bin/env python3
"""Scent Scout collector.

Reads every store in stores.json, turns its products into one common format and writes
docs/data/prices.json for the website. Runs on GitHub Actions on a schedule.

If one store fails, the others still update and that store keeps its last good prices
(marked as stale) instead of disappearing from the site.
"""
import datetime as dt
import json
import os
import re
import threading
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import normalize as N  # noqa: E402
import scent as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "collector" / "stores.json"
OUT = ROOT / "docs" / "data" / "prices.json"
HISTORY = ROOT / "data" / "history.json"
PAGE_CACHE = ROOT / "data" / "product_pages.json"   # last structured data read from each ARC product page
OVERRIDES = ROOT / "collector" / "scent_overrides.json"

UA = "ScentScout/1.0 (personal price comparison; +https://github.com/NeonInc/scent-scout)"
DELAY = 1.2          # seconds between requests to the same store, to stay polite
MAX_VARIATIONS = 300  # cap on extra WooCommerce variation lookups per run

# Stores are collected at the same time, one thread each, so each thread gets its own connection.
_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.5"})
    return _local.s


def log(*a):
    print(*a, flush=True)


def get(url, params=None, as_json=True, delay=None):
    last = None
    for attempt in range(3):
        try:
            r = _session().get(url, params=params, timeout=40)
            time.sleep(DELAY if delay is None else delay)
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
    out = {k: v for k, v in li.items() if v not in (None, "") or k in ("p", "st")}
    sx = S.extract(desc_text)
    if sx[0] or sx[1]:
        out["_sx"] = sx  # notes for the scent profile; removed before writing
    return out


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


# ---------- Dynamicweb Rapido (ARC) ----------
# 1. Each category page has a "Show more" button whose data-feed-url points at the JSON feed the page
#    uses for its product grid. The feed lists every product once, at one size, and its price can be
#    out of date during promotions.
# 2. So for perfumes the collector then opens each product page and reads its structured data
#    (schema.org ProductGroup -> one Product per bottle size, each with its live price and stock),
#    the same data ARC publishes for Google. Gift sets and mists keep the feed price.
#    Reading ~900 pages takes over half an hour, so each run reads pages for at most PAGE_BUDGET
#    seconds, oldest first, and remembers what it read in data/product_pages.json. Products not
#    refreshed this run use their remembered page (if under PAGE_MAX_AGE days old), else the feed.

PAGE_DELAY = 0.8          # seconds between ARC product pages
PAGE_BUDGET = 12 * 60     # seconds of product-page reading per run
PAGE_MAX_AGE = 4          # days a remembered product page stays usable


def rand(text):
    """'R3 000,00' -> 3000.0"""
    m = re.search(r"(\d[\d\s\u00a0.]*)(?:,(\d{2}))?", text or "")
    if not m:
        return None
    whole = re.sub(r"[\s\u00a0.]", "", m.group(1))
    return money(f"{whole}.{m.group(2) or '00'}")


def dw_image(store, path):
    """Same resized image ARC's own product grid uses. The feed's path is form-encoded ('+' = space)."""
    path = requests.utils.unquote((path or "").replace("+", " "))
    if not path:
        return ""
    return (f"//{store['url'].split('://')[1]}/Admin/Public/GetImage.ashx?width=300&height=300&crop=5&Compression=75"
            f"&FillCanvas=true&DoNotUpscale=true&Format=webp&image={requests.utils.quote(path, safe='/')}")


def ld_variants(html):
    """Every schema.org Product with an offer on a product page: size, price, stock, url, sku, barcode."""
    out = []
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html or "", re.S):
        try:
            stack = [json.loads(block)]
        except ValueError:
            continue
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                stack.extend(o)
                continue
            if not isinstance(o, dict):
                continue
            if o.get("@type") == "Product" and o.get("offers"):
                off = o["offers"][0] if isinstance(o["offers"], list) else o["offers"]
                avail = str(off.get("availability", ""))
                price = money(off.get("price"))
                if price:
                    out.append({"size": str(o.get("size") or ""), "price": price, "url": off.get("url") or o.get("url") or "",
                                "stock": not re.search(r"OutOfStock|SoldOut|Discontinued", avail), "sku": o.get("sku") or "",
                                "gtin": o.get("gtin13") or o.get("gtin") or ""})
            stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
    return out


def dw_feed_products(store):
    """All products in the category feeds, keyed by product id, with the first gender category seen."""
    products = {}
    for entry in store["paths"]:
        html = get(store["url"] + entry["path"], as_json=False)
        m = re.search(r'data-feed-url="/Default\.aspx\?ID=(\d+)', html)
        if not m:
            raise RuntimeError(f"no product feed on {entry['path']}")
        feed_id, page, pages = m.group(1), 1, 1
        while page <= pages and page <= 60:
            data = get(store["url"] + "/Default.aspx", params={
                "ID": feed_id, "feed": "true", "DoNotShowVariantsAsSingleProducts": "True", "pagesize": 100, "pagenum": page})
            block = data[0] if isinstance(data, list) and data else {}
            pages = int(block.get("totalPages") or 1)
            items = [p for c in block.get("ProductsContainer", []) for p in c.get("Product", [])]
            for p in items:
                pid = p.get("productId")
                if not pid or pid in products:
                    continue
                try:
                    brand = json.loads(p.get("googleImpression") or "{}").get("brand", "")
                except ValueError:
                    brand = ""
                price = money(p.get("priceDouble")) or rand(p.get("price"))
                # On a special, the feed's "discount" field holds the original price.
                was = rand(p.get("discount")) if p.get("onSale", "u-hidden") != "u-hidden" else None  # "" = on sale
                products[pid] = {"pid": pid, "title": N.strip_html(p.get("name", "")), "brand": brand or p.get("brand", ""),
                                 "price": price, "was": was or rand(p.get("priceRRP")), "size": p.get("variantName") or "",
                                 "variant": p.get("variantid") or "", "link": p.get("link") or "", "image": p.get("image"),
                                 "stock": "out" not in (p.get("stockState") or "") and "out of stock" not in (p.get("stockText") or "").lower(),
                                 "tags": {"m": "men", "f": "women", "u": "unisex"}.get(entry.get("g"), "")}
            log(f"  {store['id']} {entry['path']} page {page}/{pages}: {len(items)} products")
            page += 1
    return products


def collect_dynamicweb(store, clock=time.monotonic, now=None):
    out, pages_read, pages_failed, from_cache = [], 0, 0, 0
    products = [p for p in dw_feed_products(store).values() if p["price"] and not N.is_excluded(p["title"])]
    cache = json.loads(PAGE_CACHE.read_text()) if PAGE_CACHE.exists() else {}
    now = now or dt.datetime.now(dt.timezone.utc)
    want = [p for p in products if N.kind_of(p["title"]) == "p" and p["link"]]
    want.sort(key=lambda p: cache.get(p["link"], {}).get("t", ""))  # never read first, then oldest
    started, fresh = clock(), {}
    for p in want:
        if clock() - started > PAGE_BUDGET:
            break
        try:
            fresh[p["link"]] = ld_variants(get(store["url"] + p["link"], as_json=False, delay=PAGE_DELAY))
            cache[p["link"]] = {"t": now.isoformat(timespec="seconds"), "v": fresh[p["link"]]}
            pages_read += 1
        except RuntimeError as e:
            pages_failed += 1
            log(f"  {store['id']} product page failed, using feed price: {e}")
    cutoff = (now - dt.timedelta(days=PAGE_MAX_AGE)).isoformat()
    live = {p["link"] for p in products}
    for link in list(cache):  # forget pages for products ARC no longer lists, and very old ones
        if link not in live or cache[link].get("t", "") < cutoff:
            del cache[link]
    PAGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PAGE_CACHE.write_text(json.dumps(cache, separators=(",", ":"), sort_keys=True))
    for p in products:
        common = dict(title=p["title"], brand_raw=p["brand"], img=dw_image(store, p["image"]), tags_text=p["tags"])
        variants = fresh.get(p["link"])
        if variants is None and p["link"] in cache:
            variants = cache[p["link"]]["v"]
            from_cache += 1
        if variants:
            for v in variants:
                size = v["size"].upper().replace(" ", "")
                # The feed's price is ARC's regular price for its listed size; a lower page price is a promotion.
                same = size == p["size"].upper().replace(" ", "")
                was = p["was"] if same and p["was"] else (p["price"] if same and v["price"] < p["price"] - 0.5 else None)
                out.append(make_listing(
                    store, pid=f"{p['pid']}-VOLVOL{size}" if size else f"{p['pid']}-{v['sku'] or 'x'}", price=v["price"], was=was,
                    stock=v["stock"], url=v["url"] or store["url"] + p["link"], variant_text=size.replace("ML", " ml"), **common))
        else:
            out.append(make_listing(
                store, pid=f"{p['pid']}-{p['variant'] or 'x'}", price=p["price"], was=p["was"], stock=p["stock"],
                url=store["url"] + p["link"], variant_text=p["size"].replace("ML", " ml"), **common))
    log(f"  {store['id']}: read {pages_read} product pages ({pages_failed} failed), {from_cache} from earlier runs")
    return out


COLLECTORS = {"shopify": collect_shopify, "woocommerce": collect_woocommerce, "vtex": collect_vtex, "dynamicweb": collect_dynamicweb}


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


def make_profiles(listings, previous):
    """Scent profiles for every fragrance. Fragrances whose store failed this run keep yesterday's profile."""
    overrides = {k: v for k, v in json.loads(OVERRIDES.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    profiles = S.build_profiles(listings, overrides)
    live = {li["k"] for li in listings}
    for key, p in previous.items():
        if key not in profiles and key.rsplit("|", 1)[0] in live:
            profiles[key] = p
    for li in listings:
        li.pop("_sx", None)
    log(f"Scent profiles: {len(profiles)}")
    return profiles


# ---------- smaller file for the website ----------
# The site downloads prices.json on every first visit, so repeated text is factored out:
# - each store's image addresses share a long start and end, kept once in stores[].img = [start, end];
# - a listing's title "t" is dropped when it adds no words beyond brand + name + size;
# - scent profiles refer to a shared list of "smells like" lines and note names by number.

_WORD = re.compile(r"[a-z0-9]+")
_FILLER = {"ml", "for", "the", "by", "and", "de", "spray", "eau", "parfum", "toilette", "edp", "edt", "perfume", "fragrance",
           "men", "women", "man", "woman", "pour", "homme", "femme", "unisex", "natural", "vaporisateur", "new"}


def _words(text):
    text = re.sub(r"(\d+)(?:[.,]\d+)?\s*ml\b", r"\1", N.fold(text or ""))  # "100ml" -> "100"
    return {w for w in _WORD.findall(text) if w not in _FILLER}


def compact(stores_out, listings, profiles):
    by_store = {}
    for li in listings:
        if li.get("i"):
            by_store.setdefault(li["s"], []).append(li["i"])
    for s in stores_out:
        s.pop("img", None)
        imgs = by_store.get(s["id"], [])
        if len(imgs) < 20:
            continue
        pre = os.path.commonprefix(imgs)
        suf = os.path.commonprefix([x[::-1] for x in imgs])[::-1]
        shortest = min(len(x) for x in imgs)
        if len(pre) + len(suf) > shortest:
            suf = ""
        if len(pre) + len(suf) >= 12:
            s["img"] = [pre, suf]
    affix = {s["id"]: s["img"] for s in stores_out if s.get("img")}
    out = []
    for li in listings:
        li = dict(li)
        a = affix.get(li["s"])
        if a and li.get("i", "").startswith(a[0]) and li["i"].endswith(a[1]):
            li["i"] = li["i"][len(a[0]):len(li["i"]) - len(a[1])]
        if li.get("t") and _words(li["t"]) <= _words(f"{li.get('b', '')} {li.get('n', '')} {li.get('ml') or ''} {li.get('ib') or ''}"):
            del li["t"]
        out.append(li)
    phrases, notes, pidx, nidx, prof_out = [], [], {}, {}, {}
    for key, p in profiles.items():
        p = dict(p)
        if isinstance(p.get("l"), str):
            if p["l"] not in pidx:
                pidx[p["l"]] = len(phrases)
                phrases.append(p["l"])
            p["l"] = pidx[p["l"]]
        if p.get("n") and isinstance(p["n"][0], str):
            ids = []
            for n in p["n"]:
                if n not in nidx:
                    nidx[n] = len(notes)
                    notes.append(n)
                ids.append(nidx[n])
            p["n"] = ids
        prof_out[key] = p
    return out, prof_out, phrases, notes


def expand(data):
    """Undo compact() for a file written earlier (used for stores that fail and keep yesterday's prices)."""
    affix = {s["id"]: s["img"] for s in data.get("stores", []) if s.get("img")}
    for li in data.get("listings", []):
        a = affix.get(li["s"])
        if a and li.get("i"):
            li["i"] = a[0] + li["i"] + a[1]
        li.setdefault("t", li.get("n", ""))
    phrases, notes = data.get("phrases") or [], data.get("notes") or []
    for p in (data.get("profiles") or {}).values():
        if isinstance(p.get("l"), int) and p["l"] < len(phrases):
            p["l"] = phrases[p["l"]]
        if p.get("n") and isinstance(p["n"][0], int):
            p["n"] = [notes[i] for i in p["n"] if i < len(notes)]
    for s in data.get("stores", []):
        s.pop("img", None)
    return data


def collect_store(store, now):
    """One store, start to finish. Returns (listings, error)."""
    log(f"Collecting {store['name']}…")
    try:
        items = COLLECTORS[store["platform"]](store)
        if not items:
            raise RuntimeError("no products found")
        log(f"  -> {store['name']}: {len(items)} listings")
        return items, None
    except Exception as e:  # keep going with the other stores
        traceback.print_exc()
        return None, e


def main(only=None):
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    previous = expand(json.loads(OUT.read_text())) if OUT.exists() else {"listings": [], "stores": []}
    prev_by_store = {}
    for li in previous.get("listings", []):
        prev_by_store.setdefault(li["s"], []).append(li)
    prev_status = {s["id"]: s for s in previous.get("stores", [])}

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    today = now.astimezone(dt.timezone(dt.timedelta(hours=2))).date().isoformat()
    todo = [s for s in cfg["stores"] if not only or s["id"] in only]
    # Every store at once: each one is still read politely (one request at a time, with pauses),
    # but a run now takes as long as the slowest store instead of all of them added up.
    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as pool:
        results = dict(zip([s["id"] for s in todo], pool.map(lambda s: collect_store(s, now), todo)))

    all_listings, stores_out = [], []
    for store in cfg["stores"]:
        if store["id"] not in results:
            all_listings += prev_by_store.get(store["id"], [])
            stores_out.append(prev_status.get(store["id"], {"id": store["id"], "name": store["name"]}))
            continue
        info = {k: store[k] for k in ("id", "name", "url", "delivery")}
        items, err = results[store["id"]]
        if err is None:
            info.update(status="ok", count=len(items), updated=now.isoformat())
            all_listings += items
        else:
            old = prev_by_store.get(store["id"], [])
            for li in old:
                li["stale"] = True
            all_listings += old
            info.update(status="error", error=str(err)[:200], count=len(old),
                        updated=prev_status.get(store["id"], {}).get("updated"))
            log(f"  !! {store['name']} failed: {err} (kept {len(old)} old listings)")
        stores_out.append(info)

    fresh = [li for li in all_listings if not li.get("stale")]
    N.split_by_gender(fresh)
    N.infer_sizes_by_price(fresh)
    N.apply_size_assumptions(fresh)
    update_history(all_listings, today)
    profiles = make_profiles(all_listings, previous.get("profiles", {}))
    small, prof_small, phrases, notes = compact(stores_out, all_listings, profiles)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated": now.isoformat(), "stores": stores_out, "listings": small,
                               "profiles": prof_small, "phrases": phrases, "notes": notes},
                              ensure_ascii=False, separators=(",", ":")))
    ok = sum(1 for s in stores_out if s.get("status") == "ok")
    log(f"Done: {len(all_listings)} listings, {ok}/{len(stores_out)} stores updated.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:]) or None))
