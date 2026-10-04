"""Turn messy store product text into comparable fields.

Everything here is a pure function so it can be tested without the network.
"""
import html
import json
import re
import unicodedata
from pathlib import Path

_BRANDS = json.loads((Path(__file__).parent / "brands.json").read_text(encoding="utf-8"))["aliases"]
# Longest aliases first so "hugo boss fragrances" wins over "boss".
_ALIASES = sorted(_BRANDS.items(), key=lambda kv: -len(kv[0]))


# ---------- text helpers ----------

def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fold(s):
    """Lowercase, remove accents and apostrophes ("Lynk'd" -> "lynkd", "Idôle" -> "idole")."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[’'`´]", "", s)
    return s


# ---------- brand ----------

def norm_brand(raw, title=""):
    """Map a store's brand/vendor to one display name. Falls back to spotting a known brand in the title."""
    b = fold(raw).strip()
    if b in _BRANDS:
        return _BRANDS[b]
    for alias, name in _ALIASES:
        if b and (b.startswith(alias + " ") or b == alias):
            return name
    t = fold(title)
    for alias, name in _ALIASES:
        if len(alias) > 3 and re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", t):
            return name
    raw = (raw or "").strip()
    if not raw:
        return ""
    return raw if not raw.isupper() and not raw.islower() else raw.title()


def brand_aliases(brand):
    """All lowercase spellings that map to this display brand, plus the brand itself."""
    out = {fold(brand)}
    for alias, name in _BRANDS.items():
        if name == brand:
            out.add(alias)
    return sorted(out, key=len, reverse=True)


# ---------- size ----------

_ML = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:ml|mls|millilit(?:re|er)s?)(?![a-z])", re.I)
_OZ = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:fl\.?\s*)?oz(?![a-z])", re.I)
_MULTI = re.compile(r"\b\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*ml", re.I)


def sizes_in(text):
    """Every ml size mentioned in the text, in order (ounces converted)."""
    out = []
    for m in _ML.finditer(text or ""):
        v = float(m.group(1).replace(",", "."))
        if 0.5 <= v <= 1000:
            out.append(int(round(v)))
    if not out:
        for m in _OZ.finditer(text or ""):
            v = float(m.group(1).replace(",", ".")) * 29.5735
            out.append(int(round(v / 5.0) * 5) if v > 20 else int(round(v)))
    return out


def size_from_description(desc_text):
    """Only trust a description size if it's near the top, or the description mentions just one size."""
    sizes = sizes_in(desc_text[:300])
    if sizes:
        return sizes[0]
    all_sizes = set(sizes_in(desc_text))
    if len(all_sizes) == 1:
        return all_sizes.pop()
    return None


# ---------- product type ----------

_EXCLUDE = re.compile(
    r"\b(candle|diffus+er|reed|bakh?oo?r|bakhour|incense|burner|gift ?card|voucher|blind ?box|figure|plush|"
    r"keychain|key ?ring|lotion|shower|body wash|body butter|body cream|hand cream|balm|soap|shampoo|conditioner|"
    r"gummies|organi[sz]er|pouch|cosmetic bag|deo(?:dorant)?|anti-?perspirant|aftershave balm|after ?shave lotion|"
    r"hand wash|car freshener|air freshener|room spray|mug|tumbler|lipstick|lip balm|mascara|serum|merch|water bottle)\b",
    re.I,
)
_FRAGRANCE_HINT = re.compile(
    r"edp|edt|edc|parfum|perfume|cologne|eau de|fragrance|extrait|attar|oud|mist|\d+\s*ml|elixir|intense",
    re.I,
)
_SET = re.compile(r"\b(gift ?set|set|coffret|trio|duo|kit|discovery|sampler|collection box)\b", re.I)
_MIST = re.compile(r"\b(body|hair) mist\b|\bbody spray\b|\bmist\b|\bsplash\b", re.I)
_OIL = re.compile(r"\b(perfume oil|oil perfume|concentrated oil|attar|ittar|\boil\b)", re.I)


def is_excluded(text):
    return bool(_EXCLUDE.search(text or ""))


def looks_like_fragrance(text):
    return bool(_FRAGRANCE_HINT.search(text or "")) and not is_excluded(text)


def kind_of(title, extra="", variant=""):
    """p = perfume, set = gift set, mist = body mist, oil = perfume oil.
    The size-count check looks at the product title only: a variant size plus the title size isn't a set."""
    t = f"{title} {variant} {extra}"
    if _SET.search(title or "") or _MULTI.search(title or "") or len(set(sizes_in(title))) > 1:
        return "set"
    if _MIST.search(t):
        return "mist"
    if _OIL.search(title or "") or re.search(r"oil perfumes?", extra or "", re.I):
        return "oil"
    return "p"


# ---------- concentration ----------

_CONC = [
    ("Extrait", re.compile(r"\bextrait\b|\bextract de parfum", re.I)),
    ("EDP", re.compile(r"eau de parfum|\bedp\b", re.I)),
    ("EDT", re.compile(r"eau de toilette|\bedt\b", re.I)),
    ("EDC", re.compile(r"eau de cologne|\bedc\b|\bcologne\b", re.I)),
    ("Parfum", re.compile(r"\bparfum\b|\bpure perfume\b", re.I)),
]


def concentration(*texts):
    for text in texts:
        if not text:
            continue
        for name, rx in _CONC:
            if rx.search(text):
                return name
    return ""


# ---------- gender ----------

def gender_of(*texts):
    t = fold(" ".join(x for x in texts if x))
    if "unisex" in t or ("women" in t and re.search(r"\bmen\b", t)):
        return "u"
    if re.search(r"\bwom[ae]n\b|\bladies\b|\bher\b|femme\b|\bgirl", t):
        return "f"
    if re.search(r"\bm[ae]n\b|\bhim\b|homme\b|\bmens\b|\bboy\b", t):
        return "m"
    return ""


# ---------- "inspired by" ----------

_INSPIRED = re.compile(
    r"(?:inspired\s+by|inspired\s+b\b|inpired\s+by|insp\.?\s+by|impression\s+of|alternative\s+to|dupe\s+of|similar\s+to)"
    r"\s*[:\-–]?\s*([^)\n]{2,70})",
    re.I,
)


def inspired_by(title, desc_text=""):
    for text in (title, (desc_text or "")[:600]):
        m = _INSPIRED.search(text or "")
        if m:
            v = re.split(r"\s{2,}|\. |\(|\bTop notes?\b|\bNotes?:", m.group(1))[0]
            v = v.strip(" -–:.,)")
            if 2 <= len(v) <= 70:
                return v
    return ""


# ---------- names & comparison key ----------

_CONC_PHRASES = re.compile(
    r"\b(extrait de parfum|extract de parfum|eau de parfum|eau de toilette|eau de cologne|edp|edt|edc|extrait|"
    r"parfum intense|spray|vaporisateur|vapo|natural spray|tester|unboxed|refillable|refill)\b",
    re.I,
)
_DROP_TOKENS = {
    "for", "by", "the", "and", "&", "new", "natural", "men", "women", "man", "woman", "mens", "womens",
    "unisex", "pour", "fragrance", "fragrances", "perfume", "perfumes", "ml", "with",
}


def _remove_inspired(t):
    return re.split(r"\(?\s*(?:inspired\s+by|inspired\s+b\b|inpired\s+by|insp\.?\s+by|dupe\s+of)", t, flags=re.I)[0]


def display_name(title, brand):
    """Title without brand, size and 'inspired by' tail, for showing on the page."""
    t = _remove_inspired(title or "")
    for alias in brand_aliases(brand):
        t = re.sub(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", " ", t, flags=re.I)
    t = _ML.sub(" ", t)
    t = re.sub(r"\(\s*\)", " ", t)
    t = re.sub(r"\s*[-–|,/]\s*$", "", t.strip())
    t = re.sub(r"^\s*[-–|,/:]\s*", "", t)
    t = re.sub(r"\s+by\s*$", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–")
    return t or title


def name_key(title, brand):
    """Lowercase key used to put the same fragrance from different stores together."""
    t = fold(_remove_inspired(title or ""))
    for alias in brand_aliases(brand):
        t = re.sub(r"(?<![a-z0-9])" + re.escape(fold(alias)) + r"(?![a-z0-9])", " ", t)
    t = _ML.sub(" ", t)
    t = _OZ.sub(" ", t)
    t = _CONC_PHRASES.sub(" ", t)
    t = t.replace("mont blanc", "montblanc")
    t = re.sub(r"\bperfume(?=[a-z]{3})", "", t)  # "PerfumeLynked Freedom" -> "Lynked Freedom"
    t = re.sub(r"\b(\d+)\s+pm\b", r"\1pm", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    toks = [x for x in t.split() if x not in _DROP_TOKENS]
    # A trailing "parfum" is the concentration ("Bottled Absolu Parfum"), unless it's the whole name ("Le Parfum").
    if len(toks) > 1 and toks[-1] == "parfum" and any(x not in {"le", "la", "l", "the"} for x in toks[:-1]):
        toks = toks[:-1]
    key = " ".join(toks).strip()
    return key or re.sub(r"[^a-z0-9 ]+", " ", fold(title)).strip()


def group_key(brand, title):
    return f"{fold(brand)}|{name_key(title, brand)}"


# ---------- size assumption ----------

def apply_size_assumptions(listings):
    """For perfume listings with no size anywhere: the most expensive listing of the same
    fragrance at the same store is assumed to be the 100ml. A lone listing is also assumed 100ml.
    Every assumed size is marked ms='a' so the page can label it."""
    groups = {}
    for li in listings:
        if li.get("ml") or li.get("kd") != "p":
            continue
        groups.setdefault((li["s"], li["k"], li.get("c", "")), []).append(li)
    for items in groups.values():
        items.sort(key=lambda x: -x["p"])
        items[0]["ml"] = 100
        items[0]["ms"] = "a"
    return listings
