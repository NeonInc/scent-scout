"""Offline tests: run the collector against small copies of each store's real response format."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))
import collect as C  # noqa: E402
import normalize as N  # noqa: E402
import scent as S  # noqa: E402
from collections import Counter  # noqa: E402

FIX = json.loads((ROOT / "tests" / "fixtures" / "stores.json").read_text())


def fake_get(url, params=None, as_json=True):
    params = params or {}
    if "pandaperfumes" in url:
        return FIX["panda"] if params.get("page", 1) == 1 else {"products": []}
    if "rioperfumes" in url:
        return FIX["rio"] if params.get("page", 1) == 1 else {"products": []}
    if "edgars" in url:
        return FIX["edgars"] if params.get("page", 1) == 1 else {"products": []}
    if "dubaiperfumecafe" in url:
        if url.endswith("/products/9001"):
            return FIX["dpc_var_9001"]
        if url.endswith("/products/9002"):
            return FIX["dpc_var_9002"]
        return FIX["dpc"] if params.get("page", 1) == 1 else []
    if "bash.com" in url:
        return FIX["bash"] if params.get("_from", 0) == 0 and "men/grooming" in url else []
    raise AssertionError(url)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok -", msg)


def test_keys():
    pairs = [
        (("Azzaro", "Azzaro The Most Wanted Eau de Parfum Intense 100ml"), ("Azzaro", "The Most Wanted EDP Intense")),
        (("Montblanc", "Mont Blanc Explorer EDP 100ml"), ("Montblanc", "Explorer Eau de Parfum")),
        (("Afnan", "Afnan 9 PM Night Out EDP"), ("Afnan Perfumes", "9pm Night Out by Afnan 100ml")),
        (("Afnan", "Lynk'd Freedom by Afnan"), ("Afnan", "Afnan LYNKD Freedom Eau de Parfum 100ml")),
        (("Hugo Boss", "BOSS Bottled Absolu Parfum 100ml"), ("Hugo Boss Fragrances", "Hugo Boss Boss Bottled Absolu Parfum")),
        (("Armaf", "Club de Nuit Intense Man by Armaf (Inspired by Aventus by Creed)"), ("Armaf", "Armaf Club De Nuit Intense Eau de Toilette")),
        (("Armani", "Emporio Armani - Stronger With You Intensely Eau de Parfum"), ("Giorgio Armani", "Stronger With You Intensely EDP 50ml")),
    ]
    for (b1, t1), (b2, t2) in pairs:
        k1 = N.group_key(N.norm_brand(b1, t1), t1)
        k2 = N.group_key(N.norm_brand(b2, t2), t2)
        check(k1 == k2, f"same fragrance key: {t1!r} ~ {t2!r} -> {k1}")
    check(N.group_key("Rasasi", "Hawas for Him") != N.group_key("Rasasi", "Hawas for Her"), "Hawas Him/Her stay separate")
    check(N.name_key("Le Parfum Edp 30ml", "Elie Saab") == "le parfum", "Elie Saab Le Parfum keeps its name")
    check(N.sizes_in("Hawas 3.4 oz") == [100], "3.4oz -> 100ml")
    ls = [{"s": "bash", "k": "hugo boss|bottled absolu", "kd": "p", "p": 3465.0},
          {"s": "edgars", "k": "hugo boss|bottled absolu", "kd": "p", "p": 3465.0, "ml": 200, "ms": "l"}]
    N.infer_sizes_by_price(ls)
    check(ls[0]["ml"] == 200 and ls[0]["ms"] == "m", "unsized listing borrows size from same-price listing elsewhere")
    check(N.norm_brand("", "Monarc by CEVI (Inspired by CREED AVENTUS)") != "Creed", "brand never taken from the inspired-by text")
    check(N.kind_of("Azzaro Forever Wanted Absolu 100ml", "", "50ML") == "p", "variant size + title size is not a set")
    check(N.kind_of("Siyate The Nostalgia Collection Set EDP 6x 15ml") == "set", "6x15ml is a set")
    check(N.kind_of("Women's Secret Intimate Daydream 100ml & Body Lotion Gift Set") == "set", "gift set detected")
    check(N.kind_of("Sol de Janeiro Cheirosa 62 Perfume Mist") == "mist", "mist detected")
    check(N.is_excluded("Lattafa Bakhoor Khamrah"), "bakhoor excluded")
    check(not N.is_excluded("Moschino Toy Boy EDP"), "Toy Boy perfume not excluded")
    check(N.concentration("Bottled Absolu Parfum") == "Parfum", "Parfum concentration")
    check(N.concentration("La Vie Est Belle Eau De Parfum") == "EDP", "EDP before Parfum")
    check(N.inspired_by("Asad by Lattafa (Inspired by Sauvage Elixir Dior)") == "Sauvage Elixir Dior", "inspired-by from title")
    check(N.inspired_by("Siyate Set", "Black tea and spices inspired by the familiar ritual of chai") == "", "marketing 'inspired by' ignored")
    check(N.inspired_by("Al Absar Mina EDP 100ml", "INPIRED BY CHANEL - Chance Eau Spendide EDP") .startswith("CHANEL"), "inspired-by from description")


def test_gender_split():
    lis = [{"k": "davidoff|cool water", "t": t, "g": g} for t, g in [
        ("Cool Water Man Eau de Toilette", "m"), ("Cool Water Woman Eau de Toilette", "f"),
        ("Davidoff Cool Water 125ml EDT", "m"), ("Davidoff Cool Water EDT", "")]]
    lis.append({"k": "tom ford|ombre leather", "t": "Tom Ford Ombre Leather Parfum", "g": "m"})
    lis.append({"k": "tom ford|ombre leather", "t": "Tom Ford Ombré Leather Eau de Parfum", "g": "f"})
    N.split_by_gender(lis)
    check([li["k"] for li in lis[:4]] == ["davidoff|cool water men", "davidoff|cool water women", "davidoff|cool water men", "davidoff|cool water"],
          "men's and women's versions split when titles say so; untagged listing stays")
    check(lis[4]["k"] == lis[5]["k"] == "tom ford|ombre leather", "no split from store categories alone")
    check(N.is_excluded("Anny Nail Polish 15ML") and N.is_excluded("Cartier Apres Rasage 100ml After Shave splash")
          and not N.is_excluded("Paris Corner Marshmallow Blush 50ml"), "cosmetics and aftershave excluded, 'Blush' perfumes kept")


def test_scent():
    notes, acc = S.extract("Top notes: Bergamot, Lemon. Heart: Rosemary, Lavender. Base notes: Vetiver, Cedar.")
    check({"bergamot", "lemon", "rosemary", "lavender", "vetiver", "cedar"} <= notes, "notes read from a notes list")
    notes, _ = S.extract("Orange Blossom and Rosemary over Amberwood")
    check("orange blossom" in notes and "orange" not in notes and "rose" not in notes and "amber" not in notes,
          "longest note wins (orange blossom, rosemary, amberwood)")
    notes, _ = S.extract("Smokeless and drip less, fresh inspiration for a date night in the rain. Wrapped in an orange box.")
    check(not notes, "ordinary words aren't notes unless the text lists notes")
    _, acc = S.extract("Executor by Bujairami is a Woody Spicy fragrance for men.")
    check(acc == {"woo", "spi"}, "scent family words from 'is a Woody Spicy fragrance'")
    _, acc = S.extract("Profile: Floral • Fruity • Elegant • Musky INSPIRED BY Dior J'adore")
    check(acc == {"flo", "fru", "mus"}, "scent family words from 'Profile:'")
    p = S.build_profile(Counter({"lemon": 2, "bergamot": 2, "sea notes": 2, "grapefruit": 1, "cedar": 1}), Counter())
    check("su" in p["s"] and p["d"] == "d" and "beach" in p["l"], "citrus + sea notes = summer, daytime, beach line")
    p = S.build_profile(Counter({"vanilla": 2, "amber": 2, "tonka bean": 2, "benzoin": 1, "cinnamon": 1}), Counter())
    check(p["s"][-1] == "wi" and p["d"] == "n", "vanilla + amber = winter, evening")
    check(S.build_profile(Counter({"lemon": 1}), Counter()) is None, "too few notes gives no profile")
    p = S.build_profile(Counter({"vanilla": 3, "lavender": 3, "mint": 2, "sea notes": 2}), Counter())
    check(p["s"] not in (["su", "wi"], ["sp", "au"]), "seasons are only paired with a neighbour")
    lis = [
        {"k": "x|y", "c": "EDP", "s": "a", "kd": "p", "_sx": ({"lemon", "bergamot", "vetiver"}, set())},
        {"k": "x|y", "c": "EDP", "s": "a", "kd": "p", "_sx": ({"lemon", "bergamot", "vetiver"}, set())},
        {"k": "x|y", "c": "EDP", "s": "b", "kd": "p", "_sx": ({"lemon", "grapefruit", "cedar"}, set())},
        {"k": "x|y", "c": "", "s": "b", "kd": "set", "_sx": ({"vanilla", "amber", "oud"}, set())},
    ]
    prof = S.build_profiles(lis, {"x|y": {"like": "Something Famous"}})
    base = prof["x|y|"]
    check(base["n"][0] == "Lemon" and "Vanilla" not in base["n"], "notes counted once per store; gift sets ignored")
    check("x|y|EDP" not in prof and base.get("like") == "Something Famous", "duplicate concentration profile dropped; override kept")


def test_collect(tmp):
    C.get = fake_get
    C.OUT = tmp / "prices.json"
    C.HISTORY = tmp / "history.json"
    rc = C.main()
    data = json.loads(C.OUT.read_text())
    L = {li["id"]: li for li in data["listings"]}
    check(rc == 0 and all(s["status"] == "ok" for s in data["stores"]), "all fixture stores ok")

    set_ = L["panda-1"]
    check(set_["kd"] == "set", "Panda 6x15ml set is a set")
    mina = L["panda-3"]
    check(mina["ml"] == 100 and mina["ms"] == "l" and mina["c"] == "EDP", "Panda Mina 100ml EDP from title")
    check(mina.get("ib", "").lower().startswith("chanel"), "Panda inspired-by from description")

    creed = L["rio-11"]
    check(creed["ml"] == 100 and creed["b"] == "Creed", "Rio Creed 100ml")
    dolores = L["rio-12"]
    check(dolores["p"] == 250 and dolores["w"] == 800 and not dolores["st"], "Rio special price + out of stock")

    g30 = L["edgars-21"]
    check(g30["ml"] == 30 and g30["p"] == 1276 and g30["w"] == 1595, "Edgars variant size + was price")
    check(g30.get("dl") == "Multi-buy deal on site", "Edgars multi-buy tag")

    asad_big, asad_small = L["dpc-31"], L["dpc-32"]
    check(asad_big["ml"] == 100 and asad_big["ms"] == "a", "DPC: dearer of two unsized listings assumed 100ml")
    check(asad_small.get("ml") is None, "DPC: cheaper unsized listing left as unknown size")
    check(L["dpc-9001"]["ml"] == 50 and L["dpc-9002"]["ml"] == 100, "DPC variable product sizes from variations")
    check("dpc-33" not in L, "DPC bakhoor category excluded")
    check(L["dpc-34"]["p"] == 850 and L["dpc-34"]["w"] == 1200, "DPC sale price in rand")

    cdni = [li for li in data["listings"] if li["s"] == "bash" and "Club" in li["t"]]
    check(sorted(li["ml"] for li in cdni) == [105, 200], "Bash CDNI two sizes")
    check(cdni[0]["k"] == L["dpc-34"]["k"], "Bash CDNI groups with DPC CDNI")
    check(all("since" not in li for li in data["listings"]), "compact history fields")
    check(L["rio-11"]["u"].startswith("/products/"), "store URLs stored relative")
    check(all("_sx" not in li for li in data["listings"]), "private note data not written")
    check(data["profiles"].get("lattafa|asad|", {}).get("like") == "Dior Sauvage Elixir", "hand-checked 'often compared to' applied")
    size = C.OUT.stat().st_size
    print(f"fixture output: {len(L)} listings, {size} bytes")


if __name__ == "__main__":
    import tempfile
    test_keys()
    test_scent()
    test_gender_split()
    with tempfile.TemporaryDirectory() as d:
        test_collect(Path(d))
    print("ALL PASSED")
