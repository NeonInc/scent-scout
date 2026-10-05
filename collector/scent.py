"""Scent profiles: what a fragrance smells like, worked out from the notes the stores list.

Each store description is scanned for perfume notes ("bergamot", "vanilla", "oud" …) and for
scent-family words ("Woody Spicy fragrance", "Profile: Floral • Fruity"). Notes map to friendly
families (Citrus, Fresh, Green, Sweet …), and the families decide the seasons, the time of day and
a short "smells like" line. Nothing is copied from the store text except the note names.
"""
import re
from collections import Counter

# ---------- notes ----------
# family codes: cit citrus, fre fresh/aquatic, grn green, hrb herbal/aromatic, flo floral, fru fruity,
# swe sweet/gourmand, spi spicy, woo woody, oud oud, amb warm amber/resins, lea leather & smoky,
# mus musky & clean, boo boozy
_NOTES = {
    # citrus
    "bergamot": "cit", "lemon": "cit", "lime": "cit", "orange": "cit", "blood orange": "cit", "bitter orange": "cit",
    "mandarin": "cit", "mandarin orange": "cit", "tangerine": "cit", "clementine": "cit", "grapefruit": "cit",
    "citron": "cit", "yuzu": "cit", "neroli": "cit", "petitgrain": "cit", "citrus": "cit", "citruses": "cit",
    "lemon verbena": "cit", "verbena": "cit", "lemongrass": "cit", "kumquat": "cit",
    # fresh / aquatic
    "sea notes": "fre", "sea salt": "fre", "salt": "fre", "marine notes": "fre", "marine": "fre", "aquatic": "fre",
    "aquatic notes": "fre", "water notes": "fre", "ozonic notes": "fre", "ozone": "fre", "calone": "fre",
    "seaweed": "fre", "mint": "fre", "peppermint": "fre", "spearmint": "fre", "cucumber": "fre", "ambroxan": "fre",
    # green
    "green notes": "grn", "violet leaf": "grn", "violet leaves": "grn", "galbanum": "grn", "grass": "grn",
    "fig leaf": "grn", "fig": "grn", "tea": "grn", "green tea": "grn", "black tea": "grn", "mate": "grn",
    "bamboo": "grn", "tomato leaf": "grn", "ivy": "grn", "oakmoss": "grn", "moss": "grn", "basil": "grn",
    "green apple": "grn", "matcha": "grn", "blackcurrant leaf": "grn",
    # herbal / aromatic
    "lavender": "hrb", "lavandin": "hrb", "rosemary": "hrb", "sage": "hrb", "clary sage": "hrb", "thyme": "hrb",
    "geranium": "hrb", "artemisia": "hrb", "juniper": "hrb", "juniper berries": "hrb", "davana": "hrb",
    "tarragon": "hrb", "elemi": "hrb", "fougere": "hrb", "aromatic notes": "hrb", "shiso": "hrb",
    # floral
    "rose": "flo", "bulgarian rose": "flo", "damask rose": "flo", "turkish rose": "flo", "taif rose": "flo",
    "jasmine": "flo", "jasmine sambac": "flo", "tuberose": "flo", "iris": "flo", "orris": "flo", "orris root": "flo",
    "violet": "flo", "lily": "flo", "lily of the valley": "flo", "lily-of-the-valley": "flo", "magnolia": "flo",
    "peony": "flo", "orange blossom": "flo", "ylang-ylang": "flo", "ylang ylang": "flo", "freesia": "flo",
    "gardenia": "flo", "lilac": "flo", "mimosa": "flo", "osmanthus": "flo", "orchid": "flo", "carnation": "flo",
    "frangipani": "flo", "lotus": "flo", "honeysuckle": "flo", "white flowers": "flo", "floral notes": "flo",
    "heliotrope": "flo", "hibiscus": "flo", "cherry blossom": "flo", "water lily": "flo", "narcissus": "flo",
    "plumeria": "flo", "cyclamen": "flo", "lavender absolute": "hrb",
    # fruity
    "apple": "fru", "red apple": "fru", "pear": "fru", "peach": "fru", "raspberry": "fru", "blackcurrant": "fru",
    "black currant": "fru", "cassis": "fru", "pineapple": "fru", "plum": "fru", "cherry": "fru", "black cherry": "fru",
    "strawberry": "fru", "melon": "fru", "mango": "fru", "apricot": "fru", "lychee": "fru", "litchi": "fru",
    "red berries": "fru", "berries": "fru", "blackberry": "fru", "blueberry": "fru", "red fruits": "fru",
    "tropical fruits": "fru", "passion fruit": "fru", "passionfruit": "fru", "banana": "fru", "pomegranate": "fru",
    "grape": "fru", "watermelon": "fru", "guava": "fru", "quince": "fru", "nectarine": "fru", "fruity notes": "fru",
    "papaya": "fru",
    # sweet / gourmand
    "vanilla": "swe", "bourbon vanilla": "swe", "madagascar vanilla": "swe", "tonka": "swe", "tonka bean": "swe",
    "caramel": "swe", "praline": "swe", "chocolate": "swe", "dark chocolate": "swe", "cacao": "swe", "cocoa": "swe",
    "coffee": "swe", "honey": "swe", "sugar": "swe", "brown sugar": "swe", "cotton candy": "swe", "candy": "swe",
    "almond": "swe", "bitter almond": "swe", "pistachio": "swe", "marshmallow": "swe", "popcorn": "swe",
    "milk": "swe", "toffee": "swe", "coconut": "swe", "hazelnut": "swe", "chestnut": "swe", "meringue": "swe",
    "biscuit": "swe", "cookie": "swe", "gourmand notes": "swe", "creamy notes": "swe", "benzoin": "amb",
    "maple": "swe", "nougat": "swe", "licorice": "swe", "liquorice": "swe",
    # spicy
    "pepper": "spi", "pink pepper": "spi", "black pepper": "spi", "sichuan pepper": "spi", "cinnamon": "spi",
    "cardamom": "spi", "saffron": "spi", "nutmeg": "spi", "clove": "spi", "cloves": "spi", "ginger": "spi",
    "cumin": "spi", "star anise": "spi", "anise": "spi", "chili": "spi", "coriander": "spi", "spices": "spi",
    "spicy notes": "spi", "caraway": "spi", "elemi resin": "amb",
    # woody
    "cedar": "woo", "cedarwood": "woo", "atlas cedar": "woo", "virginia cedar": "woo", "sandalwood": "woo",
    "vetiver": "woo", "patchouli": "woo", "birch": "woo", "guaiac wood": "woo", "guaiac": "woo", "cashmeran": "woo",
    "cashmere wood": "woo", "cypress": "woo", "oak": "woo", "pine": "woo", "pine needles": "woo", "woody notes": "woo",
    "woods": "woo", "amberwood": "woo", "papyrus": "woo", "cypriol": "woo", "driftwood": "woo", "teak": "woo",
    "rosewood": "woo", "ebony": "woo", "fir": "woo", "akigalawood": "woo", "iso e super": "woo", "mahogany": "woo",
    "ambrofix": "woo", "cedar leaves": "woo",
    # oud
    "oud": "oud", "agarwood": "oud", "oudh": "oud", "agar wood": "oud", "oud accord": "oud",
    # warm amber / resins
    "amber": "amb", "ambergris": "amb", "labdanum": "amb", "incense": "amb", "olibanum": "amb",
    "frankincense": "amb", "myrrh": "amb", "resins": "amb", "resin": "amb", "styrax": "amb", "opoponax": "amb",
    "balsam": "amb", "tolu balsam": "amb", "peru balsam": "amb", "black amber": "amb",
    # leather & smoky
    "leather": "lea", "suede": "lea", "tobacco": "lea", "tobacco leaf": "lea", "smoke": "lea", "birch tar": "lea",
    "cade": "lea", "cade oil": "lea", "smoky notes": "lea", "castoreum": "lea", "guaiac smoke": "lea",
    # musky & clean
    "musk": "mus", "white musk": "mus", "musks": "mus", "ambrette": "mus", "aldehydes": "mus", "cotton": "mus",
    "cotton flower": "mus", "powdery notes": "mus", "clean notes": "mus", "cashmere": "mus",
    # boozy
    "cognac": "boo", "rum": "boo", "whisky": "boo", "whiskey": "boo", "wine": "boo", "champagne": "boo",
    "gin": "boo", "bourbon": "boo", "brandy": "boo", "boozy notes": "boo", "cognac accord": "boo", "absinthe": "boo",
}
# Words that are both a note and ordinary English; only counted when the text clearly lists notes.
_AMBIGUOUS = {"orange", "salt", "cotton", "candy", "milk", "woods",
              "pine", "oak", "rose", "lily", "fig", "tea", "mate", "ivy", "moss", "cashmere", "grape", "spices",
              "cherry", "honey", "sugar", "smoke", "pepper", "wine", "gin", "citrus", "berries"}
# Some notes are in almost everything (bergamot, amber, musk) or very loud (oud, leather, vanilla).
NOTE_WEIGHT = {
    "bergamot": .6, "amber": .6, "musk": .6, "white musk": .6, "musks": .6, "ambergris": .7, "cedar": .8,
    "cedarwood": .8, "patchouli": .8, "floral notes": .6, "fruity notes": .6, "woody notes": .6, "spicy notes": .6,
    "oud": 2, "agarwood": 2, "oudh": 2, "oud accord": 2, "leather": 1.5, "suede": 1.3, "tobacco": 1.4,
    "vanilla": 1.4, "bourbon vanilla": 1.4, "madagascar vanilla": 1.4, "caramel": 1.3, "coffee": 1.3,
    "incense": 1.3, "rum": 1.2, "cognac": 1.2, "whisky": 1.2, "saffron": 1.2, "tuberose": 1.2,
    "sea notes": 1.3, "marine notes": 1.3, "aquatic notes": 1.3, "mint": 1.2, "lavender": 1.2,
}

_NOTE_RX = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(n) for n in sorted(_NOTES, key=len, reverse=True)) + r")(?![a-z])"
)
_NOTES_HINT = re.compile(r"\b(top|heart|middle|base)\s*notes?\b|\bnotes?\s*(?:are|is|:)|\b(top|heart|base)\s*:", re.I)

# Scent-family words stores use, e.g. "is a Woody Spicy fragrance" or "Profile: Woody • Spicy".
_ACCORD_WORDS = {
    "woody": "woo", "spicy": "spi", "floral": "flo", "fruity": "fru", "gourmand": "swe", "sweet": "swe",
    "aromatic": "hrb", "fougere": "hrb", "fougère": "hrb", "citrus": "cit", "citrusy": "cit", "aquatic": "fre",
    "fresh": "fre", "amber": "amb", "ambery": "amb", "oriental": "amb", "leather": "lea", "leathery": "lea",
    "chypre": "woo", "green": "grn", "musky": "mus", "powdery": "mus", "oud": "oud", "smoky": "lea",
    "vanilla": "swe", "warm": "amb", "spiced": "spi", "marine": "fre", "boozy": "boo",
}
_ACCORD_RX = [
    re.compile(r"\bis an? ((?:[A-Z][a-zè]+[ -]){1,4})fragrance"),
    re.compile(r"\b(?:profile|accords?|olfactory family|fragrance family|scent family)\s*:\s*([A-Za-zè ,&•·/|-]{3,80})", re.I),
]


def extract(desc):
    """(notes, accords) found in one store description: two sets of note names and family codes."""
    if not desc:
        return set(), set()
    text = desc[:4000]
    low = text.lower()
    listed = bool(_NOTES_HINT.search(text))
    notes = set()
    for m in _NOTE_RX.finditer(low):
        n = m.group(1)
        if n in _AMBIGUOUS and not listed:
            continue
        notes.add(n)
    accords = set()
    for rx in _ACCORD_RX:
        for m in rx.finditer(text):
            for w in re.split(r"[\s,&•·/|-]+", m.group(1).lower()):
                if w in _ACCORD_WORDS:
                    accords.add(_ACCORD_WORDS[w])
    return notes, accords


# ---------- profile from many listings ----------

SEASON_WEIGHTS = {
    "spring": {"flo": 3, "grn": 3, "fru": 2, "cit": 1.5, "hrb": 1, "mus": 1.2, "fre": 1},
    "summer": {"cit": 3, "fre": 3, "grn": 1.5, "fru": 1.5, "hrb": 1, "flo": .5, "mus": .5},
    "autumn": {"woo": 2.5, "spi": 2.5, "lea": 2, "amb": 2, "boo": 2, "swe": 1.5, "hrb": 1, "oud": 2, "fru": .5},
    "winter": {"amb": 3, "swe": 2.5, "spi": 2, "lea": 2.5, "boo": 2.5, "oud": 2.5, "woo": 1.5},
}
DAY = {"cit", "fre", "grn", "hrb", "mus", "flo", "fru"}
NIGHT = {"swe", "amb", "lea", "boo", "oud", "spi"}

LABEL = {
    "cit": "Citrusy", "fre": "Fresh & airy", "grn": "Green vibes", "hrb": "Herbal", "flo": "Floral", "fru": "Fruity",
    "swe": "Sweet", "spi": "Spicy", "woo": "Woody", "oud": "Oud", "amb": "Warm & ambery", "lea": "Leathery & smoky",
    "mus": "Clean & musky", "boo": "Boozy",
}

LINE = {
    "cit": "a squeeze of fresh lemon on a hot summer's day",
    "fre": "a sea breeze on a clear, sunny morning",
    "grn": "a walk through a garden after the rain",
    "hrb": "a freshly cut herb garden: crisp, clean and classic",
    "flo": "a bouquet of fresh flowers",
    "fru": "a bowl of ripe, juicy fruit",
    "swe": "a dessert bar: vanilla, caramel and warm sweetness",
    "spi": "a spice market: warm, peppery and bold",
    "woo": "a cedar cabin in the forest",
    "oud": "rich, smoky oud: deep and luxurious",
    "amb": "a cosy evening by the fire, with a hint of incense",
    "lea": "a new leather jacket and a whisper of smoke",
    "mus": "fresh laundry and clean skin",
    "boo": "a glass of cognac in a leather armchair",
}
PAIR = {
    "cit+fre": "a summer day at the beach: zesty citrus and sea air",
    "cit+woo": "fresh citrus over smooth, clean woods: sharp and polished",
    "cit+hrb": "a crisp, barbershop-clean freshness",
    "cit+grn": "freshly picked limes and green leaves",
    "cit+flo": "a sunny garden with orange trees in bloom",
    "cit+fru": "an ice-cold fruit punch on a summer afternoon",
    "cit+swe": "lemon tart: bright zest with a sweet, creamy finish",
    "cit+spi": "zesty citrus with a spicy kick",
    "cit+mus": "a crisp white shirt straight off the washing line",
    "amb+cit": "bright citrus melting into a warm, glowing base",
    "cit+lea": "fresh citrus over a smooth leather jacket",
    "cit+oud": "bright citrus over dark, smoky oud",
    "fre+woo": "a walk on the beach past driftwood: fresh, airy and clean",
    "fre+hrb": "a cool mountain breeze through wild herbs",
    "flo+fre": "fresh flowers by the ocean",
    "fre+fru": "a cold fruity drink by the pool",
    "fre+mus": "fresh-out-the-shower clean",
    "fre+spi": "a cool breeze with a peppery spark",
    "fre+swe": "a sea breeze with a soft, sweet finish",
    "fre+grn": "dewy grass and fresh morning air",
    "amb+fre": "sun-warmed skin after a day at the beach",
    "fre+lea": "a fresh breeze over smooth leather",
    "grn+woo": "a forest walk: leaves, moss and damp wood",
    "flo+grn": "a spring garden in full bloom",
    "grn+hrb": "a freshly cut herb garden",
    "fru+grn": "fruit picked straight from the tree",
    "grn+mus": "clean linen drying in a green field",
    "grn+swe": "green tea with a spoon of honey",
    "grn+spi": "fresh leaves with a peppery bite",
    "hrb+woo": "a classic gentleman's barbershop",
    "hrb+spi": "warm spices and fresh lavender",
    "hrb+swe": "lavender and vanilla: soft, warm and comforting",
    "amb+hrb": "lavender by a crackling fire",
    "flo+hrb": "a herb and flower garden in spring",
    "hrb+lea": "a barbershop with leather chairs",
    "hrb+mus": "freshly ironed shirts and a clean shave",
    "flo+fru": "a fruity bouquet: playful, bright and pretty",
    "flo+swe": "flowers and candy: sweet, soft and romantic",
    "flo+woo": "fresh flowers on a polished wooden table: elegant and soft",
    "flo+mus": "soft petals on clean skin: powdery and elegant",
    "flo+spi": "spiced rose: warm and a little mysterious",
    "amb+flo": "a rose garden at dusk: warm and rich",
    "flo+lea": "roses and soft suede",
    "flo+oud": "rose and oud: rich, deep and luxurious",
    "fru+swe": "a fruity dessert: juicy and sugary",
    "fru+woo": "juicy fruit over smooth woods: confident and modern",
    "fru+spi": "spiced fruit punch",
    "fru+mus": "a juicy, clean fruit mist",
    "amb+fru": "dried fruit and warm amber",
    "fru+lea": "juicy fruit with a smoky, leathery edge",
    "boo+fru": "fruit soaked in rum",
    "fru+oud": "dark fruit and smoky oud",
    "swe+woo": "vanilla and warm wood: cosy and smooth",
    "spi+swe": "a warm cinnamon bun: sweet, spicy and cosy",
    "amb+swe": "a cosy winter night in: warm vanilla and amber",
    "mus+swe": "warm, sweet skin: soft and cuddly",
    "lea+swe": "sweet tobacco and leather: rich and smooth",
    "boo+swe": "a boozy dessert: rum, caramel and vanilla",
    "oud+swe": "sweet oud: rich, smooth and addictive",
    "spi+woo": "a crackling log fire with warm spices",
    "amb+spi": "an Arabian spice market at night",
    "lea+spi": "a leather jacket with a kick of pepper",
    "mus+spi": "warm spice on clean skin",
    "boo+spi": "spiced rum by the fire",
    "oud+spi": "saffron and oud: bold and regal",
    "amb+woo": "incense and warm wood: deep and smooth",
    "lea+woo": "a leather armchair in a wood-panelled study",
    "mus+woo": "clean skin and soft woods: subtle and polished",
    "boo+woo": "whisky aged in an oak barrel",
    "oud+woo": "precious dark woods: rich and smoky",
    "amb+lea": "smoky incense and dark leather: bold evening wear",
    "amb+mus": "warm skin and soft amber: cosy and close",
    "amb+boo": "cognac by the fire",
    "amb+oud": "oud and incense: rich and regal",
    "lea+mus": "soft suede and clean skin",
    "boo+lea": "a whisky bar with leather chairs",
    "lea+oud": "smoky oud and dark leather",
    "mus+oud": "soft musk with a dark, smoky heart",
}
SEASON_ORDER = ["spring", "summer", "autumn", "winter"]


def family_scores(note_counts, accord_counts):
    scores = Counter()
    for n, c in note_counts.items():
        scores[_NOTES[n]] += c * NOTE_WEIGHT.get(n, 1)
    for a, c in accord_counts.items():
        scores[a] += 3 * c
    return scores


def build_profile(note_counts, accord_counts, min_notes=3):
    """note_counts: Counter of note -> number of stores listing it. accord_counts: Counter of family codes.
    Returns a compact dict for the site, or None when there's too little to go on."""
    if len(note_counts) < min_notes and sum(accord_counts.values()) < 2:
        return None
    sc = family_scores(note_counts, accord_counts)
    if not sc:
        return None
    total = sum(sc.values())
    fams = [f for f, v in sc.most_common() if v / total >= 0.12][:3] or [sc.most_common(1)[0][0]]
    # seasons: the best one, plus the runner-up when it's nearly as strong
    ss = {s: sum(w.get(f, 0) * v for f, v in sc.items()) for s, w in SEASON_WEIGHTS.items()}
    ranked = sorted(ss, key=lambda s: (-ss[s], SEASON_ORDER.index(s)))
    first, second = ranked[0], ranked[1]
    neighbours = abs(SEASON_ORDER.index(first) - SEASON_ORDER.index(second)) == 1
    seasons = [first] + ([second] if neighbours and ss[second] >= 0.8 * ss[first] else [])
    seasons.sort(key=SEASON_ORDER.index)
    day = sum(v for f, v in sc.items() if f in DAY)
    night = sum(v for f, v in sc.items() if f in NIGHT)
    when = "day" if day >= 1.6 * night else "night" if night >= 1.6 * day else "both"
    line = None
    if len(fams) > 1:
        line = PAIR.get("+".join(sorted(fams[:2])))
    line = line or LINE[fams[0]]
    # Most-listed notes first; generic ones ("floral notes") only when there's room.
    notes = [n for n, _ in sorted(note_counts.items(), key=lambda kv: (-kv[1], n_generic(kv[0]), -NOTE_WEIGHT.get(kv[0], 1), kv[0]))][:6]
    return {
        "f": fams,
        "s": [s[:2] for s in seasons],  # sp su au wi
        "d": when[0],                    # d / n / b
        "l": line,
        "n": [_display(n) for n in notes],
    }


def n_generic(n):
    return 1 if n.endswith(" notes") or n in ("woods", "spices", "resins", "musks", "berries") else 0


def _display(n):
    return " ".join(w if w in ("of", "the") else w[:1].upper() + w[1:] for w in n.split(" "))


def build_profiles(listings, overrides=None):
    """Profiles keyed by 'groupkey|concentration' and by 'groupkey|' (all concentrations together).
    Uses each listing's private '_sx' = (notes, accords) and counts each note once per store."""
    per = {}
    for li in listings:
        sx = li.get("_sx")
        if not sx or li.get("kd") not in ("p", "oil"):
            continue
        notes, accords = sx
        for key in {f"{li['k']}|{li.get('c', '')}", f"{li['k']}|"}:
            bucket = per.setdefault(key, {})
            st = bucket.setdefault(li["s"], [set(), set()])
            st[0] |= notes
            st[1] |= accords
    out = {}
    for key, by_store in per.items():
        nc, ac = Counter(), Counter()
        for notes, accords in by_store.values():
            nc.update(notes)
            ac.update(accords)
        p = build_profile(nc, ac)
        if p:
            out[key] = p
    for key, extra in (overrides or {}).items():
        for full in [k for k in out if k == key or k.startswith(key + "|")] or [key + "|"]:
            out.setdefault(full, {}).update(extra)
    # A concentration profile identical to the all-concentrations one is dropped to save space.
    for key in list(out):
        base = key.rsplit("|", 1)[0] + "|"
        if key != base and out.get(base) == out[key]:
            del out[key]
    return out
