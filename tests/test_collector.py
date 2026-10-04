"""Offline tests: run the collector against small copies of each store's real response format."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "collector"))
import collect as C  # noqa: E402
import normalize as N  # noqa: E402

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
    check(N.kind_of("Siyate The Nostalgia Collection Set EDP 6x 15ml") == "set", "6x15ml is a set")
    check(N.kind_of("Women's Secret Intimate Daydream 100ml & Body Lotion Gift Set") == "set", "gift set detected")
    check(N.kind_of("Sol de Janeiro Cheirosa 62 Perfume Mist") == "mist", "mist detected")
    check(N.is_excluded("Lattafa Bakhoor Khamrah"), "bakhoor excluded")
    check(not N.is_excluded("Moschino Toy Boy EDP"), "Toy Boy perfume not excluded")
    check(N.concentration("Bottled Absolu Parfum") == "Parfum", "Parfum concentration")
    check(N.concentration("La Vie Est Belle Eau De Parfum") == "EDP", "EDP before Parfum")
    check(N.inspired_by("Asad by Lattafa (Inspired by Sauvage Elixir Dior)") == "Sauvage Elixir Dior", "inspired-by from title")
    check(N.inspired_by("Al Absar Mina EDP 100ml", "INPIRED BY CHANEL - Chance Eau Spendide EDP") .startswith("CHANEL"), "inspired-by from description")


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
    check(asad_small["ml"] is None, "DPC: cheaper unsized listing left as unknown size")
    check(L["dpc-9001"]["ml"] == 50 and L["dpc-9002"]["ml"] == 100, "DPC variable product sizes from variations")
    check("dpc-33" not in L, "DPC bakhoor category excluded")
    check(L["dpc-34"]["p"] == 850 and L["dpc-34"]["w"] == 1200, "DPC sale price in rand")

    cdni = [li for li in data["listings"] if li["s"] == "bash" and "Club" in li["t"]]
    check(sorted(li["ml"] for li in cdni) == [105, 200], "Bash CDNI two sizes")
    check(cdni[0]["k"] == L["dpc-34"]["k"], "Bash CDNI groups with DPC CDNI")
    check(all("lo" in li for li in data["listings"]), "history fields attached")
    size = C.OUT.stat().st_size
    print(f"fixture output: {len(L)} listings, {size} bytes")


if __name__ == "__main__":
    import tempfile
    test_keys()
    with tempfile.TemporaryDirectory() as d:
        test_collect(Path(d))
    print("ALL PASSED")
