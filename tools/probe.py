"""Fetch a few store pages from GitHub Actions and save what comes back, to see how each store serves its data."""
import json
import re
import sys
from pathlib import Path

import requests

UA = "ScentScout/1.0 (personal price comparison; +https://github.com/NeonInc/scent-scout)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
OUT = Path("probe")
OUT.mkdir(exist_ok=True)
targets = json.loads(Path(sys.argv[1]).read_text())

for name, url in targets.items():
    for label, ua in (("bot", UA), ("browser", BROWSER_UA)):
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}, timeout=40)
            body = r.text
            info = {"url": url, "ua": label, "status": r.status_code, "final_url": r.url, "bytes": len(body),
                    "content_type": r.headers.get("content-type"), "server": r.headers.get("server")}
            # Pull out anything that looks like embedded product data.
            hints = {
                "json_ld_blocks": len(re.findall(r'application/ld\+json', body)),
                "next_data": "__NEXT_DATA__" in body,
                "initial_state": bool(re.search(r"__INITIAL_STATE__|__PRELOADED_STATE__|window\.__APOLLO", body)),
                "price_mentions": len(re.findall(r"R\s?\d[\d,\s]*\.\d\d|\"price\"", body)),
                "api_paths": sorted(set(re.findall(r'["\'](/api/[a-zA-Z0-9_/\-]{3,60})', body)))[:40],
            }
            info["hints"] = hints
            (OUT / f"{name}.{label}.json").write_text(json.dumps(info, indent=1))
            (OUT / f"{name}.{label}.body.txt").write_text(body[:600000])
            print(name, label, r.status_code, len(body), hints["price_mentions"])
        except Exception as e:
            (OUT / f"{name}.{label}.json").write_text(json.dumps({"url": url, "error": str(e)}))
            print(name, label, "ERROR", e)
